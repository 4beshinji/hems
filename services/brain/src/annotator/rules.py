"""Seed regex rules for shopping category classification.

Categories align with FrequentPlace.category values:
  drugstore | supermarket | convenience | home_center | other

Order matters — more specific patterns are matched first.
"""

import re

SHOP_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(シャンプー|リンス|コンディショナー|化粧水|乳液|美容液|日焼け|日焼止"
            r"|マスク|歯ブラシ|歯磨|マウスウォッシュ|デンタル"
            r"|コンタクト|目薬|点眼|うがい薬"
            r"|サプリ|ビタミン|プロテイン|医薬品|胃薬|鎮痛|風邪薬|解熱|湿布"
            r"|絆創膏|ガーゼ|消毒|オロナイン"
            r"|生理用|ナプキン|綿棒|爪切り)"
        ),
        "drugstore",
    ),
    (
        re.compile(
            r"(電球|LED電球|蛍光灯|乾電池|単三|単四|ボタン電池"
            r"|養生テープ|ガムテープ|結束バンド|延長コード"
            r"|工具|ドライバー|ペンチ|釘|ネジ|ボルト"
            r"|ペンキ|塗料|のこぎり|やすり|ホームセンター"
            r"|プランター|園芸|肥料|培養土|観葉植物|鉢|プラスチックケース"
            r"|収納ボックス|ゴミ袋|ポリ袋|水やり)"
        ),
        "home_center",
    ),
    (
        re.compile(
            r"(おにぎり|弁当|サンドイッチ|カップ麺|カップラーメン"
            r"|コンビニ|切手|収入印紙|コピー用紙|公共料金)"
        ),
        "convenience",
    ),
    (
        re.compile(
            r"(牛乳|ヨーグルト|バター|チーズ|生クリーム|卵|たまご"
            r"|食パン|パン|米|お米|玄米"
            r"|肉|豚肉|牛肉|鶏肉|ミンチ|ひき肉|ハム|ベーコン|ソーセージ"
            r"|野菜|キャベツ|にんじん|玉ねぎ|じゃがいも|トマト|きゅうり|レタス"
            r"|魚|鮭|さけ|マグロ|サバ|さば|イワシ|エビ|刺身"
            r"|豆腐|納豆|油揚げ|厚揚げ"
            r"|醤油|しょうゆ|味噌|みそ|砂糖|塩|みりん|酢"
            r"|食用油|オリーブオイル|ごま油|サラダ油"
            r"|パスタ|うどん|そば|中華麺"
            r"|惣菜|お惣菜|冷凍食品|冷凍餃子|カレー|ルー|ふりかけ"
            r"|お茶|麦茶|緑茶|紅茶|コーヒー豆|インスタントコーヒー"
            r"|ジュース|麦茶|炭酸水|ペットボトル水|ミネラルウォーター"
            r"|ビール|発泡酒|日本酒|焼酎|ワイン|チューハイ)"
        ),
        "supermarket",
    ),
]


def match_rule(name: str) -> str | None:
    """Return first-matching category, else None."""
    if not name:
        return None
    for pattern, category in SHOP_RULES:
        if pattern.search(name):
            return category
    return None
