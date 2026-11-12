"""FotoYek indirilebilir yapay zekâ paketleri.

  fotoyek-yuz.onnx   GFPGAN v1.4 yüz onarımı (Apache-2.0, TencentARC/GFPGAN). Girdi 1×3×512×512 RGB [-1,1], çıktı aynı.
  fotoyek-renk.onnx  DDColor-tiny renklendirme (Apache-2.0, piddnad/DDColor). Girdi 1×3×512×512 gri RGB [0,1], çıktı 1×2×512×512 Lab ab.

İndirme boyutu yarıya insin diye ağırlıklar float16 saklanır; hesap float32 yapılır (her ağırlığın önünde bir Cast düğümü var,
ONNX Runtime yüklerken bunları bir kez float32'ye çevirir). Her paketin çıktısı PyTorch'taki özgün modelle karşılaştırılır.
"""
import hashlib
import json
import os
import sys
import time
import urllib.request

import numpy as np
import onnx
import onnxruntime as ort
import torch
from onnx import TensorProto, helper, numpy_helper
from PIL import Image
from skimage import color, data

sys.path.insert(0, "stub")
os.makedirs("out", exist_ok=True)
rapor = []


def yaz(s):
    print(s, flush=True)
    rapor.append(s)


def indir(url, yol):
    if not os.path.exists(yol):
        urllib.request.urlretrieve(url, yol)
    v = open(yol, "rb").read()
    yaz(f"kaynak {os.path.basename(yol)}: {len(v)} bayt, sha256 {hashlib.sha256(v).hexdigest()}")
    return yol


def yari_boy(giris, cikis):
    """Büyük float32 ağırlıkları float16 saklar, önlerine float32'ye çeviren Cast düğümü ekler."""
    m = onnx.load(giris)
    g = m.graph
    yeni, dugum = [], []
    for ini in list(g.initializer):
        if ini.data_type == TensorProto.FLOAT and int(np.prod(ini.dims)) >= 1024:
            a = numpy_helper.to_array(ini)
            if np.abs(a).max() > 60000:
                continue
            yeni.append(numpy_helper.from_array(a.astype(np.float16), ini.name + "__h"))
            dugum.append(helper.make_node("Cast", [ini.name + "__h"], [ini.name], to=TensorProto.FLOAT, name=ini.name + "__cast"))
            g.initializer.remove(ini)
    g.initializer.extend(yeni)
    for d in reversed(dugum):
        g.node.insert(0, d)
    onnx.checker.check_model(m)
    onnx.save(m, cikis)
    os.remove(giris)


def oturum(yol):
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.intra_op_num_threads = 4
    return ort.InferenceSession(yol, so, providers=["CPUExecutionProvider"])


def kayit(yol):
    v = open(yol, "rb").read()
    return {"dosya": os.path.basename(yol), "boyut": len(v), "sha256": hashlib.sha256(v).hexdigest()}


paketler = {}

# ------------------------------------------------------------------ GFPGAN
from gfpgan.archs.gfpganv1_clean_arch import GFPGANv1Clean  # noqa: E402

pth = indir("https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth", "GFPGANv1.4.pth")
gfp = GFPGANv1Clean(out_size=512, num_style_feat=512, channel_multiplier=2, decoder_load_path=None, fix_decoder=False,
                    num_mlp=8, input_is_latent=True, different_w=True, narrow=1, sft_half=True)
sd = torch.load(pth, map_location="cpu")
gfp.load_state_dict(sd.get("params_ema", sd), strict=True)
gfp.eval()


class Yuz(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, x):
        return self.m(x, return_rgb=False, randomize_noise=False)[0]


yuz = Yuz(gfp).eval()
torch.manual_seed(1)
ornek = torch.rand(1, 3, 512, 512) * 2 - 1
with torch.no_grad():
    torch.onnx.export(yuz, ornek, "out/yuz32.onnx", opset_version=17, input_names=["input"], output_names=["output"],
                      do_constant_folding=True)
    beklenen = yuz(ornek).numpy()
yari_boy("out/yuz32.onnx", "out/fotoyek-yuz.onnx")
s = oturum("out/fotoyek-yuz.onnx")
t = time.time()
cikan = s.run(None, {"input": ornek.numpy()})[0]
yaz(f"yüz: en büyük fark {np.abs(cikan - beklenen).max():.4f}, ortalama {np.abs(cikan - beklenen).mean():.5f}, süre {time.time() - t:.1f} sn (4 çekirdek)")
assert np.abs(cikan - beklenen).mean() < 0.01, "yüz modeli özgününden saptı"
paketler["yuz"] = kayit("out/fotoyek-yuz.onnx")
del gfp, yuz, s

# ------------------------------------------------------------------ DDColor
from basicsr.archs.ddcolor_arch import DDColor  # noqa: E402

bin_ = indir("https://huggingface.co/piddnad/ddcolor_paper_tiny/resolve/main/pytorch_model.bin", "ddcolor_paper_tiny.bin")
dd = DDColor(encoder_name="convnext-t", decoder_name="MultiScaleColorDecoder", input_size=[512, 512], num_output_channels=2,
             last_norm="Spectral", do_normalize=False, num_queries=100, num_scales=3, dec_layers=9)
sd = torch.load(bin_, map_location="cpu")
sd = sd.get("params", sd)
eksik, fazla = dd.load_state_dict(sd, strict=False)
yaz(f"renk: eksik anahtar {len(eksik)}, fazla anahtar {len(fazla)}")
assert not eksik, eksik[:10]
dd.eval()


def gri_girdi(rgb):
    """DDColor'ın kendi akışı: 512×512'ye indir, Lab'ın yalnız L'sinden gri RGB üret."""
    k = np.asarray(Image.fromarray(rgb).resize((512, 512), Image.BILINEAR)).astype(np.float32) / 255.0
    lab = color.rgb2lab(k)
    lab[..., 1:] = 0
    g = color.lab2rgb(lab).astype(np.float32)
    return g.transpose(2, 0, 1)[None]


def renklendir(s, rgb):
    h, w, _ = rgb.shape
    ab = s.run(None, {"input": gri_girdi(rgb)})[0][0]  # 2×512×512
    ab = np.stack([np.asarray(Image.fromarray(ab[i]).resize((w, h), Image.BILINEAR)) for i in range(2)], -1)
    lab = color.rgb2lab(rgb.astype(np.float32) / 255.0)
    lab[..., 1:] = ab
    return (np.clip(color.lab2rgb(lab), 0, 1) * 255).round().astype(np.uint8)


ornek_r = torch.from_numpy(gri_girdi(data.chelsea()))
with torch.no_grad():
    torch.onnx.export(dd, ornek_r, "out/renk32.onnx", opset_version=17, input_names=["input"], output_names=["output"],
                      do_constant_folding=True)
    beklenen = dd(ornek_r).numpy()
yari_boy("out/renk32.onnx", "out/fotoyek-renk.onnx")
s = oturum("out/fotoyek-renk.onnx")
t = time.time()
cikan = s.run(None, {"input": ornek_r.numpy()})[0]
yaz(f"renk: en büyük fark {np.abs(cikan - beklenen).max():.3f}, ortalama {np.abs(cikan - beklenen).mean():.4f} (ab ölçeği ±128), süre {time.time() - t:.1f} sn")
assert np.abs(cikan - beklenen).mean() < 0.5, "renk modeli özgününden saptı"
paketler["renk"] = kayit("out/fotoyek-renk.onnx")

# Önizleme: renkli fotoğrafı griye/sepyaya çevir, renklendir; sol gri girdi, orta model, sağ özgün
for ad, img in {"kedi": data.chelsea(), "kahve": data.coffee()}.items():
    gri = (color.rgb2gray(img) * 255).astype(np.uint8)
    sepya = np.stack([gri * 1.05, gri * 0.93, gri * 0.74], -1).clip(0, 255).astype(np.uint8)
    sonuc = renklendir(s, sepya)
    Image.fromarray(np.concatenate([sepya, sonuc, img], 1)).save(f"out/onizleme-renk-{ad}.jpg", quality=90)

json.dump({"surum": 1, "paketler": paketler}, open("out/paketler.json", "w"), indent=1)
open("out/rapor.txt", "w").write("\n".join(rapor) + "\n")
print(json.dumps(paketler, indent=1))
