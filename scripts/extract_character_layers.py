#!/usr/bin/env python3
"""
PSDtool 立ち絵レイヤー抽出スクリプト

ナースロボ＿タイプＴ PSD から HEMS 2D アバター用の
透明背景 PNG をパーツ別に抽出する。

Usage:
    uv run python3 scripts/extract_character_layers.py [--zip PATH] [--out DIR]

Dependencies (uv で自動解決):
    psd-tools>=1.9.0
    Pillow>=10.0.0
"""

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "psd-tools>=1.9.0",
#   "Pillow>=10.0.0",
# ]
# ///

import argparse
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image
from psd_tools import PSDImage

ROOT = Path(__file__).parent.parent
DEFAULT_ZIP = ROOT / "ナースロボ＿タイプＴ公式立ち絵素材2.0.zip"
DEFAULT_OUT = ROOT / "services/frontend/public/assets/character/nurserobo"

# 50% 縮小 → 680×1407px
SCALE = 0.5


# ── レイヤーナビゲーション ──────────────────────────────────────────────────


def find_child(parent: Any, name: str) -> Any:
    """直下の子レイヤーを名前で検索する。"""
    for layer in parent:
        if layer.name == name:
            return layer
    available = [l.name for l in parent]
    raise KeyError(f"Layer {name!r} not found. Available: {available}")


def find_path(psd: PSDImage, path: list[str]) -> Any:
    """パスリストでレイヤーツリーを辿る。"""
    node: Any = psd
    for name in path:
        node = find_child(node, name)
    return node


def get_star_children(group: Any) -> list[Any]:
    """* プレフィックス（ラジオ選択）の子レイヤーを返す。"""
    return [l for l in group if l.name.startswith("*")]


# ── 可視性制御 ─────────────────────────────────────────────────────────────


def save_and_hide(layers: list[Any]) -> dict[int, bool]:
    originals: dict[int, bool] = {}
    for l in layers:
        originals[id(l)] = l.visible
        l.visible = False
    return originals


def save_and_show(layers: list[Any]) -> dict[int, bool]:
    originals: dict[int, bool] = {}
    for l in layers:
        originals[id(l)] = l.visible
        l.visible = True
    return originals


def restore(layers: list[Any], originals: dict[int, bool]) -> None:
    for l in layers:
        if id(l) in originals:
            l.visible = originals[id(l)]


# ── レンダリング ────────────────────────────────────────────────────────────


def composite_scaled(psd: PSDImage) -> Image.Image:
    img = psd.composite(ignore_preview=True)
    w = int(psd.width * SCALE)
    h = int(psd.height * SCALE)
    return img.resize((w, h), Image.LANCZOS)


def render_layer_isolated(psd: PSDImage, target: Any) -> Image.Image | None:
    """
    単一レイヤー（またはグループ）を透明背景・フルキャンバスサイズで抽出する。
    layer.composite(force=True) → フルキャンバスに貼り付け → スケール
    """
    orig = target.visible
    target.visible = True
    try:
        img = target.composite(force=True)
    except Exception as e:
        print(f"    WARNING: composite failed for {target.name!r}: {e}")
        target.visible = orig
        return None
    target.visible = orig

    if img is None:
        return None

    # フルキャンバスに配置（元の座標系）
    canvas = Image.new("RGBA", (psd.width, psd.height), (0, 0, 0, 0))
    canvas.paste(img, (target.left, target.top), img)

    # スケール
    w = int(psd.width * SCALE)
    h = int(psd.height * SCALE)
    return canvas.resize((w, h), Image.LANCZOS)


def render_expression(
    psd: PSDImage,
    *,
    eye_target: Any,
    brow_target: Any,
    eye_group: Any,
    brow_group: Any,
    mouth_group: Any,
    ex_group: Any,
    arm_groups: list[Any] | None = None,
) -> Image.Image:
    """
    全身＋指定目・眉（口なし、EXなし、腕なし）の表情ベース画像をレンダリングする。
    腕はオーバーレイとして別途合成するため、ベースからは除外する。
    """
    hide_layers: list[Any] = []
    show_layers: list[Any] = []

    # 口: 全子を非表示
    hide_layers.extend(get_star_children(mouth_group))

    # 目（!まつげ）: 非ターゲットを隠し、ターゲットを表示
    for l in get_star_children(eye_group):
        if l is eye_target:
            if not l.visible:
                show_layers.append(l)
        else:
            hide_layers.append(l)

    # 眉（!まゆ）: 非ターゲットを隠し、ターゲットを表示
    for l in get_star_children(brow_group):
        if l is brow_target:
            if not l.visible:
                show_layers.append(l)
        else:
            hide_layers.append(l)

    # EX エフェクト: 全て非表示（返り血・汗等はアバター状態で別途オーバーレイ）
    hide_layers.extend(list(ex_group))

    # 腕: 全て非表示（オーバーレイ���して別途合成、多腕防止）
    if arm_groups:
        for ag in arm_groups:
            hide_layers.extend(get_star_children(ag))

    orig_h = save_and_hide(hide_layers)
    orig_s = save_and_show(show_layers)

    img = composite_scaled(psd)

    restore(hide_layers, orig_h)
    restore(show_layers, orig_s)

    return img


# ── メイン処理 ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract PSDtool character layers")
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP, help="ZIP ファイルパス")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="出力ディレクトリ")
    args = parser.parse_args()

    if not args.zip.exists():
        raise FileNotFoundError(f"ZIP not found: {args.zip}")

    # ── PSD 読み込み ─────────────────────────────────────────────────────
    print(f"Loading PSD from: {args.zip.name}")
    with zipfile.ZipFile(args.zip) as z:
        psd_entry = next(n for n in z.namelist() if n.endswith(".psd"))
        data = z.read(psd_entry)

    psd = PSDImage.open(io.BytesIO(data))
    print(f"Canvas: {psd.width}×{psd.height}px → output: {int(psd.width * SCALE)}×{int(psd.height * SCALE)}px")

    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    # ── キーグループを取得 ───────────────────────────────────────────────
    face = find_path(psd, ["頭", "!顔"])
    mouth_g = find_child(face, "口")
    eye_g = find_child(face, "!まつげ")
    brow_g = find_child(face, "!まゆ")
    ex_g = find_child(face, "EX")
    body_g = find_child(psd, "!身体")
    official = find_child(body_g, "*公式服")
    patient = find_child(body_g, "*饕餮（患者着）")

    # ── 腕グループ（表情ベースから除外するため先に取得）────────────────
    arm_g = find_path(psd, ["!身体", "*公式服", "!腕", "*両腕"])
    left_arm_g = find_child(arm_g, "!左腕")
    right_arm_g = find_child(arm_g, "!右腕")

    # ── 表情×衣装の組み合わせ ──────────────────────────────────────────
    # (eye_layer_name, brow_layer_name)
    EXPRESSIONS: dict[str, tuple[str, str]] = {
        "neutral": ("*ジト目", "*普通"),
        "happy": ("*普通", "*普通"),
        "surprised": ("*O O", "*驚き"),
        "sad": ("*普通", "*悲しみ"),
        "angry": ("*ジト目", "*怒り"),
        "worried": ("*普通", "*困惑"),
    }

    (out / "expr").mkdir(exist_ok=True)
    print("\n[1/5] Expression images (costume × expression, no mouth, no arms)...")

    for expr_name, (eye_name, brow_name) in EXPRESSIONS.items():
        eye_target = find_child(eye_g, eye_name)
        brow_target = find_child(brow_g, brow_name)

        for costume_name, (show_layer, hide_layer) in [
            ("official", (official, patient)),
            ("patient", (patient, official)),
        ]:
            orig_show = save_and_show([show_layer])
            orig_hide = save_and_hide([hide_layer])

            img = render_expression(
                psd,
                eye_target=eye_target,
                brow_target=brow_target,
                eye_group=eye_g,
                brow_group=brow_g,
                mouth_group=mouth_g,
                ex_group=ex_g,
                arm_groups=[left_arm_g, right_arm_g],
            )
            fname = f"{costume_name}_{expr_name}.png"
            img.save(out / "expr" / fname, optimize=True)
            print(f"  expr/{fname}")

            restore([show_layer], orig_show)
            restore([hide_layer], orig_hide)

    # ── 目オーバーレイ（瞬き・半目・ウィンク等）─────────────────────
    EYE_VARIANTS: dict[str, str] = {
        "blink": "*閉じ　(まばたき用)",
        "closed": "*閉じ",
        "closed_smile": "*閉じ笑顔",
        "normal_half": "*普通 半閉じ",
        "jito_half": "*ジト目 半閉じ",
        "wink_r": "ウィンク右",
        "wink_l": "ウィンク左",
        "qq": "*Q Q",
        "gt_lt": "*> <",
    }

    (out / "eyes").mkdir(exist_ok=True)
    print("\n[2/9] Eye overlays (blink, half-closed, wink)...")
    extracted_eyes: list[str] = []

    for out_name, layer_name in EYE_VARIANTS.items():
        try:
            layer = find_child(eye_g, layer_name)
        except KeyError as e:
            print(f"  SKIP eyes/{out_name}.png — {e}")
            continue
        img = render_layer_isolated(psd, layer)
        if img:
            img.save(out / "eyes" / f"{out_name}.png", optimize=True)
            print(f"  eyes/{out_name}.png")
            extracted_eyes.append(out_name)

    # ── 腕オーバーレイ（公式服・左右独立）──────────────────────────
    # arm_g, left_arm_g, right_arm_g は表情ベース生成時に既に取得済み

    LEFT_ARM_VARIANTS: dict[str, str] = {
        "default": "*デフォルト",
        "down": "*下ろ",
        "syringe": "*注射器",
        "point": "*1",
        "hip": "*腰当て",
        "peace": "*ちょき",
        "open": "*ぱー",
    }

    RIGHT_ARM_VARIANTS: dict[str, str] = {
        "default": "*デフォルト",
        "hip": "*腰当て ",
        "point": "*１",
        "beckon": "*こちらへ",
        "peace": "*ちょき",
        "open": "*ぱー",
        "mouth": "*口元",
    }

    (out / "arms").mkdir(exist_ok=True)
    print("\n[3/9] Arm overlays (left + right)...")
    extracted_arms_l: list[str] = []
    extracted_arms_r: list[str] = []

    for out_name, layer_name in LEFT_ARM_VARIANTS.items():
        try:
            layer = find_child(left_arm_g, layer_name)
        except KeyError as e:
            print(f"  SKIP arms/left_{out_name}.png — {e}")
            continue
        img = render_layer_isolated(psd, layer)
        if img:
            img.save(out / "arms" / f"left_{out_name}.png", optimize=True)
            print(f"  arms/left_{out_name}.png")
            extracted_arms_l.append(out_name)

    for out_name, layer_name in RIGHT_ARM_VARIANTS.items():
        try:
            layer = find_child(right_arm_g, layer_name)
        except KeyError as e:
            print(f"  SKIP arms/right_{out_name}.png — {e}")
            continue
        img = render_layer_isolated(psd, layer)
        if img:
            img.save(out / "arms" / f"right_{out_name}.png", optimize=True)
            print(f"  arms/right_{out_name}.png")
            extracted_arms_r.append(out_name)

    # ── 口オーバーレイ ─────────────────────────────────────────────────
    MOUTH_VARIANTS: dict[str, str] = {
        "close": "*閉じ",
        "smile": "*笑",
        "hmm": "*ん",
        "smile_open": "*笑開き",
        "a": "*あ",
        "i": "*い",
        "i_smile": "*い笑",
        "u": "*う",
        "e": "*え",
        "o": "*お",
        "o_big": "*お大",
        "a_smile": "*あ笑開き",
        "ahaha": "*あはは",
        "hawawa": "*はわわ",
        "tongue": "*べろ",
        "hmph": "*ふん",
    }

    (out / "mouth").mkdir(exist_ok=True)
    print("\n[4/9] Mouth overlays...")
    extracted_mouth: list[str] = []

    for out_name, layer_name in MOUTH_VARIANTS.items():
        try:
            layer = find_child(mouth_g, layer_name)
        except KeyError as e:
            print(f"  SKIP mouth/{out_name}.png — {e}")
            continue
        img = render_layer_isolated(psd, layer)
        if img:
            img.save(out / "mouth" / f"{out_name}.png", optimize=True)
            print(f"  mouth/{out_name}.png")
            extracted_mouth.append(out_name)

    # ── EX エフェクトオーバーレイ ────────────────────────────────────
    FX_VARIANTS: dict[str, str] = {
        "tears": "涙",
        "sweat": "汗",
        "damage": "破損",
        "damage2": "破損 2",
        "blood": "血",
        "shadow": "影",
        "glow_orange": "目玉光る・オレンジ",
        "glow_red": "目玉光る・赤",
    }

    (out / "fx").mkdir(exist_ok=True)
    print("\n[5/9] FX overlays (返り血, 汗, etc.)...")
    extracted_fx: list[str] = []

    for out_name, layer_name in FX_VARIANTS.items():
        try:
            layer = find_child(ex_g, layer_name)
        except KeyError as e:
            print(f"  SKIP fx/{out_name}.png — {e}")
            continue
        img = render_layer_isolated(psd, layer)
        if img:
            img.save(out / "fx" / f"{out_name}.png", optimize=True)
            print(f"  fx/{out_name}.png")
            extracted_fx.append(out_name)

    # ── アクセサリーオーバーレイ ────────────────────────────────────
    # 装飾グループは PSD 内に複数ある — 全て走査
    deco_layers: dict[str, Any] = {}
    for top_layer in psd:
        if top_layer.name == "装飾" and top_layer.is_group():
            for child in top_layer:
                deco_layers[child.name] = child

    ACCESSORY_VARIANTS: dict[str, str] = {
        "cat_ears": "猫耳",
        "flower": "ヤグルマギク",
        "glasses": "メガネ",
    }

    (out / "accessories").mkdir(exist_ok=True)
    print("\n[6/9] Accessory overlays...")
    extracted_acc: list[str] = []

    for out_name, layer_name in ACCESSORY_VARIANTS.items():
        if layer_name not in deco_layers:
            print(f"  SKIP accessories/{out_name}.png — layer not found")
            continue
        img = render_layer_isolated(psd, deco_layers[layer_name])
        if img:
            img.save(out / "accessories" / f"{out_name}.png", optimize=True)
            print(f"  accessories/{out_name}.png")
            extracted_acc.append(out_name)

    # ── 記号オーバーレイ ────────────────────────────────────────────
    SYMBOL_VARIANTS: dict[str, str] = {
        "exclamation": "！",
        "question": "？",
        "surprise": "びっくり",
    }

    (out / "symbols").mkdir(exist_ok=True)
    print("\n[7/9] Symbol overlays...")
    extracted_sym: list[str] = []

    try:
        symbol_g = find_child(psd, "記号")
    except KeyError:
        print("  SKIP symbols (記号 group not found)")
        symbol_g = None

    if symbol_g:
        for out_name, layer_name in SYMBOL_VARIANTS.items():
            try:
                layer = find_child(symbol_g, layer_name)
            except KeyError as e:
                print(f"  SKIP symbols/{out_name}.png — {e}")
                continue
            img = render_layer_isolated(psd, layer)
            if img:
                img.save(out / "symbols" / f"{out_name}.png", optimize=True)
                print(f"  symbols/{out_name}.png")
                extracted_sym.append(out_name)

    # ── マニフェスト生成 ─────────────────────────────────────────────
    manifest = {
        "character": "nurserobo",
        "size": {
            "width": int(psd.width * SCALE),
            "height": int(psd.height * SCALE),
        },
        "source_size": {"width": psd.width, "height": psd.height},
        "scale": SCALE,
        "costumes": ["official", "patient"],
        "expressions": list(EXPRESSIONS.keys()),
        "eyes": extracted_eyes,
        "arms_left": extracted_arms_l,
        "arms_right": extracted_arms_r,
        "mouth": extracted_mouth,
        "fx": extracted_fx,
        "accessories": extracted_acc,
        "symbols": extracted_sym,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    total = (
        len(EXPRESSIONS) * 2
        + len(extracted_eyes)
        + len(extracted_arms_l)
        + len(extracted_arms_r)
        + len(extracted_mouth)
        + len(extracted_fx)
        + len(extracted_acc)
        + len(extracted_sym)
    )
    print(f"\n✓ Done! {total} PNGs + manifest.json → {out}")


if __name__ == "__main__":
    main()
