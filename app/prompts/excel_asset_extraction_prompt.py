"""Excel 资产字段抽取提示词。"""


def build_excel_asset_extraction_prompt(
    *,
    task: str,
    output_shape: str,
    rows_text: str,
) -> str:
    """构造 Excel 资产抽取提示词。"""

    row_key_rule = ""
    row_key_field = ""
    if output_shape == "array":
        row_key_rule = (
            "2. 每个输出对象必须包含输入里的 row_key，并且 row_key 必须原样返回。"
            "输入有几行，输出就必须有几个对象，不要漏行，不要合并行。"
        )
        row_key_field = '"row_key": "批量模式必须原样返回输入 row_key",'

    return f"""
你是短剧资产库的数据清洗助手。{task}

输出要求：
1. 只能输出严格 JSON，不要输出 Markdown，不要解释。
{row_key_rule}
3. 不要编造 Excel 中没有的信息；无法判断的字段用 null 或空数组。
4. asset_kind 只能是 character、scene、prop、clothing、voice、other。
5. gender 只能是 男、女、未知 或 null。
6. age_value、height_cm 必须是数字或 null。
7. approved 必须是 true、false 或 null。

字段提取规则：
1. name/display_name：资产名称。角色优先取姓名，场景优先取场景名。
2. category：用中文分类，例如 角色、场景、道具、服装、其他。
3. 基础字段必须单独对应：Excel 中的年龄、性别、身高/cm、身高、height 等字段，必须分别写入 age_value、gender、height_cm。不要把年龄、性别、身高写进 intro、appearance、hair_description、outfit_description 或 style_tags。如果原值是 "-"、"/"、空值或无法判断，则对应字段填 null。
4. intro：必须尽量完整，不要只提取一句。把 Excel 中介绍性、叙事性、关系性字段整合进 intro，包括但不限于：简介、性格特征、职业/身份、人物背景、主要经历、和其他人关系、动机和目标、结局、备注。不要因为这些字段没有独立数据库列就丢弃。intro 可以用“身份：...；性格：...；背景：...；经历：...；关系：...；动机：...；结局：...”这种短句组织，但禁止包含年龄、性别、身高。
5. appearance：保留整体外观、长相、面部特征、体态和气质；不要重复年龄、性别、身高、服装；如果 hair_description 已经提取了发型，appearance 不要重复头发颜色和发型。
6. hair_description：只能填写头发相关信息，例如发型、发色、长短、是否盘发。不要把面部特征、伤疤、肌肉、身材、体态、气质放到 hair_description，这些应放到 appearance。
7. outfit_description：只填写服装、穿着、饰品、配饰信息。
8. style_tags：积极提取可用于检索和筛选的短标签，不要只返回空数组。优先从职业/身份、性格特征、人物关系、剧情定位、角色类型、外观风格、场景类型中提取。标签应该短而明确，例如：古泰拳传人、反派、武者、路人、名媛、海外大宗师、病人、拍卖师、冷漠、油腻狂妄、叶逍遥敌人、楚家下属、复仇、争利。
9. 权重分级是内部管理字段，不要写入 intro、appearance、style_tags 或其他输出字段。

输出 JSON 字段必须包含：
{{
  {row_key_field}
  "asset_kind": "character | scene | prop | clothing | voice | other",
  "name": "资产名称",
  "display_name": "展示名称",
  "intro": "充分汇总简介、身份、性格、人物背景、主要经历、人物关系、动机目标、结局等介绍信息，不包含年龄、性别、身高",
  "appearance": "整体外观、长相、面部特征、体态和气质",
  "age_value": null,
  "gender": null,
  "height_cm": null,
  "hair_description": "仅头发、发型、发色信息",
  "outfit_description": "服装、穿着、饰品、配饰信息",
  "category": "角色/场景/道具/服装/其他",
  "style_tags": [],
  "approved": null
}}

{rows_text}
""".strip()
