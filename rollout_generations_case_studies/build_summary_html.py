#!/usr/bin/env python3
from __future__ import annotations

import html
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "index.html"


CATEGORY_META = {
    "majority vote correct": {
        "label": "Majority Correct",
        "color": "#2a7f62",
        "accent": "#dff3ea",
    },
    "majority vote wrong": {
        "label": "Majority Wrong",
        "color": "#b4561b",
        "accent": "#fff0e3",
    },
    "not-even sampled": {
        "label": "Not-even Sampled",
        "color": "#8f2d56",
        "accent": "#fde8f0",
    },
    "min/max inconsistent prompt": {
        "label": "Min/Max Inconsistent",
        "color": "#2d5f8f",
        "accent": "#e5f0fb",
    },
}


def parse_analysis(md_path: Path) -> dict:
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = lines[0].removeprefix("# ").strip()
    sections = {}
    current = None
    buffer = []

    for line in lines[1:]:
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buffer).strip()
            current = line.removeprefix("## ").strip()
            buffer = []
        else:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer).strip()

    basic_info = {}
    for raw in sections.get("基本信息", "").splitlines():
        line = raw.strip()
        if not line.startswith("- "):
            continue
        payload = line[2:]
        if ": " not in payload:
            continue
        key, value = payload.split(": ", 1)
        basic_info[key.strip()] = value.strip().strip("`")

    return {
        "title": title,
        "sections": sections,
        "basic_info": basic_info,
        "image": md_path.parent / "answer_distribution.png",
        "folder": md_path.parent.name,
        "analysis_path": md_path,
    }


def render_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def render_markdown_block(text: str) -> str:
    if not text.strip():
        return ""

    lines = text.splitlines()
    parts = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            code_text = "\n".join(code_lines)
            parts.append(
                f"<pre class='code-block'><div class='code-lang'>{html.escape(lang or 'text')}</div>"
                f"<code>{html.escape(code_text)}</code></pre>"
            )
            i += 1
            continue

        if stripped.startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(f"<li>{render_inline(lines[i].strip()[2:])}</li>")
                i += 1
            parts.append(f"<ul>{''.join(items)}</ul>")
            continue

        if re.match(r"^\d+\.\s", stripped):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s", lines[i].strip()):
                item_text = re.sub(r"^\d+\.\s", "", lines[i].strip(), count=1)
                items.append(f"<li>{render_inline(item_text)}</li>")
                i += 1
            parts.append(f"<ol>{''.join(items)}</ol>")
            continue

        para_lines = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt:
                i += 1
                break
            if nxt.startswith("```") or nxt.startswith("- "):
                break
            para_lines.append(nxt)
            i += 1
        paragraph = " ".join(para_lines)
        parts.append(f"<p>{render_inline(paragraph)}</p>")

    return "".join(parts)


def build_case_nav(cases: list[dict]) -> str:
    items = []
    for case in cases:
        anchor = case["folder"]
        meta = CATEGORY_META.get(case["basic_info"].get("分类", ""), {})
        label = meta.get("label", case["basic_info"].get("分类", "Case"))
        items.append(
            f"<a class='nav-item' href='#{anchor}'>"
            f"<span class='nav-kicker'>{html.escape(label)}</span>"
            f"<span class='nav-title'>{html.escape(case['title'])}</span>"
            f"</a>"
        )
    return "".join(items)


def build_summary_cards(cases: list[dict]) -> str:
    total = len(cases)
    distribution = {}
    for category in CATEGORY_META:
        distribution[category] = sum(1 for case in cases if case["basic_info"].get("分类") == category)

    cards = [
        ("Case Studies", str(total), f"精选 {total} 个代表性 rollout group"),
        (
            "Majority Correct",
            str(distribution["majority vote correct"]),
            "多数票能自我纠错，但单条 rollout 仍会犯错",
        ),
        (
            "Majority Wrong",
            str(distribution["majority vote wrong"]),
            "正确答案存在，但主导模板稳定出错",
        ),
        (
            "Not-even Sampled",
            str(distribution["not-even sampled"]),
            "正确解在整组 sample 中完全没有出现",
        ),
        (
            "Min/Max Inconsistent",
            str(distribution["min/max inconsistent prompt"]),
            "同一 prompt 内同时出现 maximize / minimize 两种建模方向",
        ),
    ]
    return "".join(
        "<div class='metric-card'>"
        f"<div class='metric-label'>{html.escape(label)}</div>"
        f"<div class='metric-value'>{html.escape(value)}</div>"
        f"<div class='metric-sub'>{html.escape(sub)}</div>"
        "</div>"
        for label, value, sub in cards
    )


def build_case_section(case: dict) -> str:
    category_key = case["basic_info"].get("分类", "")
    meta = CATEGORY_META.get(category_key, {"label": category_key, "color": "#4b5563", "accent": "#eef2f7"})
    info_rows = []
    ordered_keys = [
        "来源文件",
        "prompt_index",
        "分类",
        "ground truth",
        "ground truth / 正确答案",
        "majority answer",
        "sampled answer 分布",
        "错误 rollout",
        "majority 错误 rollout",
        "minority 正确 rollout",
    ]
    seen = set()
    for key in ordered_keys + list(case["basic_info"].keys()):
        if key in seen or key not in case["basic_info"]:
            continue
        seen.add(key)
        value = case["basic_info"][key]
        info_rows.append(
            "<div class='info-row'>"
            f"<div class='info-key'>{html.escape(key)}</div>"
            f"<div class='info-value'>{render_inline(value)}</div>"
            "</div>"
        )

    section_order = [
        "错误答案成因",
        "majority 错误答案成因",
        "三类回复概览",
        "原始文本片段（标出错误点）",
        "原始文本片段（majority wrong，标出错误点）",
        "minority correct 的原始文本",
        "正确答案与复核",
        "结论",
    ]
    rendered_sections = []
    for heading in section_order:
        block = case["sections"].get(heading)
        if not block:
            continue
        rendered_sections.append(
            "<section class='detail-section'>"
            f"<h3>{html.escape(heading)}</h3>"
            f"{render_markdown_block(block)}"
            "</section>"
        )

    image_rel = case["image"].relative_to(ROOT).as_posix()
    analysis_rel = case["analysis_path"].relative_to(ROOT).as_posix()

    return (
        f"<article class='case-card' id='{html.escape(case['folder'])}' style='--case-color:{meta['color']}; --case-accent:{meta['accent']};'>"
        "<div class='case-header'>"
        f"<div class='case-badge'>{html.escape(meta['label'])}</div>"
        f"<h2>{html.escape(case['title'])}</h2>"
        f"<a class='source-link' href='{html.escape(analysis_rel)}'>查看原始 analysis.md</a>"
        "</div>"
        "<div class='case-grid'>"
        f"<div class='info-card'>{''.join(info_rows)}</div>"
        "<div class='chart-card'>"
        f"<img src='{html.escape(image_rel)}' alt='answer distribution for {html.escape(case['title'])}'>"
        "</div>"
        "</div>"
        f"{''.join(rendered_sections)}"
        "</article>"
    )


def build_html(cases: list[dict]) -> str:
    nav_html = build_case_nav(cases)
    cards_html = build_summary_cards(cases)
    case_html = "".join(build_case_section(case) for case in cases)
    total = len(cases)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Rollout Case Studies</title>
  <style>
    :root {{
      --bg: #f5f1e8;
      --panel: #fffdf8;
      --line: #e8dece;
      --text: #1f2937;
      --muted: #6b7280;
      --shadow: 0 10px 30px rgba(81, 62, 35, 0.08);
      --maxw: 1400px;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(173, 139, 81, 0.12), transparent 28%),
        linear-gradient(180deg, #f6f0e3 0%, #f4efe7 48%, #f8f5ef 100%);
      font-family: Georgia, "Iowan Old Style", "Palatino Linotype", "Times New Roman", serif;
    }}
    a {{ color: inherit; }}
    code {{
      font-family: "SFMono-Regular", Menlo, Consolas, monospace;
      background: #f3eee3;
      padding: 0.08rem 0.35rem;
      border-radius: 6px;
      font-size: 0.92em;
    }}
    .page {{
      max-width: var(--maxw);
      margin: 0 auto;
      padding: 28px 24px 80px;
    }}
    .hero {{
      background:
        linear-gradient(135deg, rgba(255,255,255,0.78), rgba(255,248,235,0.92)),
        linear-gradient(135deg, #214e57, #8d5a2b);
      border: 1px solid rgba(141, 90, 43, 0.15);
      border-radius: 28px;
      box-shadow: var(--shadow);
      padding: 30px 30px 26px;
      margin-bottom: 22px;
      overflow: hidden;
      position: relative;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -80px -80px auto;
      width: 240px;
      height: 240px;
      background: radial-gradient(circle, rgba(141, 90, 43, 0.16), transparent 65%);
      border-radius: 999px;
    }}
    .eyebrow {{
      display: inline-block;
      font-size: 12px;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: #8d5a2b;
      font-weight: 700;
      margin-bottom: 14px;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(34px, 5vw, 58px);
      line-height: 0.96;
      letter-spacing: -0.03em;
      max-width: 780px;
    }}
    .hero p {{
      max-width: 760px;
      margin: 16px 0 0;
      font-size: 17px;
      line-height: 1.7;
      color: #374151;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin: 20px 0 26px;
    }}
    .metric-card {{
      background: rgba(255,255,255,0.82);
      backdrop-filter: blur(4px);
      border: 1px solid rgba(232, 222, 206, 0.95);
      border-radius: 18px;
      padding: 18px 18px 16px;
      box-shadow: 0 4px 16px rgba(73, 51, 24, 0.05);
    }}
    .metric-label {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: #8b7355;
      margin-bottom: 10px;
    }}
    .metric-value {{
      font-size: 34px;
      line-height: 1;
      font-weight: 700;
      margin-bottom: 6px;
    }}
    .metric-sub {{
      font-size: 14px;
      line-height: 1.55;
      color: var(--muted);
    }}
    .layout {{
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      gap: 22px;
      align-items: start;
    }}
    .sidebar {{
      position: sticky;
      top: 20px;
      background: rgba(255, 252, 245, 0.86);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 16px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(6px);
    }}
    .sidebar h2 {{
      margin: 4px 0 14px;
      font-size: 20px;
    }}
    .nav-item {{
      display: block;
      text-decoration: none;
      border: 1px solid transparent;
      border-radius: 16px;
      padding: 12px 12px 11px;
      transition: transform 140ms ease, border-color 140ms ease, background 140ms ease;
      margin-bottom: 8px;
      background: #fff;
    }}
    .nav-item:hover {{
      transform: translateY(-1px);
      border-color: #d7c3aa;
      background: #fff9ef;
    }}
    .nav-kicker {{
      display: block;
      font-size: 11px;
      color: #8d5a2b;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      margin-bottom: 6px;
      font-weight: 700;
    }}
    .nav-title {{
      display: block;
      font-size: 14px;
      line-height: 1.4;
      font-weight: 600;
    }}
    .content {{
      display: grid;
      gap: 22px;
    }}
    .case-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      padding: 26px;
      position: relative;
      overflow: hidden;
    }}
    .case-card::before {{
      content: "";
      position: absolute;
      inset: 0 auto 0 0;
      width: 8px;
      background: var(--case-color);
    }}
    .case-header {{
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 12px;
      align-items: center;
      margin-bottom: 18px;
    }}
    .case-badge {{
      display: inline-flex;
      align-items: center;
      background: var(--case-accent);
      color: var(--case-color);
      border: 1px solid color-mix(in srgb, var(--case-color) 20%, white);
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .case-header h2 {{
      margin: 0;
      font-size: 30px;
      line-height: 1.1;
      letter-spacing: -0.02em;
    }}
    .source-link {{
      text-decoration: none;
      font-size: 13px;
      color: var(--muted);
      border-bottom: 1px solid currentColor;
      width: fit-content;
    }}
    .case-grid {{
      display: grid;
      grid-template-columns: minmax(280px, 400px) minmax(0, 1fr);
      gap: 16px;
      margin-bottom: 18px;
    }}
    .info-card, .chart-card {{
      border-radius: 20px;
      border: 1px solid var(--line);
      background: #fff;
      overflow: hidden;
    }}
    .info-card {{
      padding: 14px 16px;
      display: grid;
      gap: 10px;
      align-content: start;
    }}
    .info-row {{
      display: grid;
      grid-template-columns: 132px 1fr;
      gap: 12px;
      align-items: start;
      padding-bottom: 10px;
      border-bottom: 1px solid #f1eadc;
    }}
    .info-row:last-child {{
      border-bottom: none;
      padding-bottom: 0;
    }}
    .info-key {{
      font-size: 12px;
      color: #8b7355;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 700;
    }}
    .info-value {{
      font-size: 14px;
      line-height: 1.55;
    }}
    .chart-card {{
      padding: 14px;
      background:
        linear-gradient(180deg, #fffdf8 0%, #fff7ea 100%);
    }}
    .chart-card img {{
      display: block;
      width: 100%;
      height: auto;
      border-radius: 12px;
      border: 1px solid #efe5d5;
      background: white;
    }}
    .detail-section {{
      margin-top: 18px;
      padding-top: 18px;
      border-top: 1px dashed #dccfb8;
    }}
    .detail-section h3 {{
      margin: 0 0 12px;
      font-size: 22px;
      letter-spacing: -0.02em;
    }}
    .detail-section p,
    .detail-section li {{
      font-size: 16px;
      line-height: 1.72;
      color: #2f3744;
    }}
    .detail-section ul {{
      margin: 10px 0 0;
      padding-left: 20px;
    }}
    .detail-section ol {{
      margin: 10px 0 0;
      padding-left: 24px;
    }}
    .code-block {{
      margin: 14px 0;
      border-radius: 18px;
      overflow: hidden;
      border: 1px solid #e2d7c3;
      background: #1e2430;
      color: #edf2f7;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.05);
    }}
    .code-lang {{
      padding: 8px 12px;
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #d7e1ef;
      background: rgba(255,255,255,0.06);
      border-bottom: 1px solid rgba(255,255,255,0.07);
      font-family: "SFMono-Regular", Menlo, Consolas, monospace;
    }}
    .code-block code {{
      display: block;
      padding: 14px 16px 16px;
      overflow-x: auto;
      white-space: pre;
      background: transparent;
      color: inherit;
      border-radius: 0;
      font-size: 13px;
      line-height: 1.6;
    }}
    .footer {{
      margin-top: 28px;
      padding: 18px 6px 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
    }}
    @media (max-width: 1120px) {{
      .layout {{
        grid-template-columns: 1fr;
      }}
      .sidebar {{
        position: static;
      }}
    }}
    @media (max-width: 780px) {{
      .page {{
        padding: 18px 14px 56px;
      }}
      .hero {{
        padding: 22px 18px;
        border-radius: 22px;
      }}
      .metrics {{
        grid-template-columns: 1fr;
      }}
      .case-card {{
        padding: 18px;
        border-radius: 22px;
      }}
      .case-header {{
        grid-template-columns: 1fr;
      }}
      .case-grid {{
        grid-template-columns: 1fr;
      }}
      .info-row {{
        grid-template-columns: 1fr;
        gap: 6px;
      }}
      .detail-section p,
      .detail-section li {{
        font-size: 15px;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="eyebrow">Rollout Error Atlas</div>
      <h1>Rollout Case Studies</h1>
      <p>这个页面把 <code>ttrl_opt/rollout_generations_case_studies</code> 里的 {total} 个代表性案例整理成一个单页汇总。阅读顺序从“多数票能纠错”到“多数票被带偏”，再到“正确答案根本没被采样到”与“同题出现 min/max 漂移”，便于横向比较错误模式。</p>
    </section>

    <section class="metrics">{cards_html}</section>

    <div class="layout">
      <aside class="sidebar">
        <h2>目录</h2>
        {nav_html}
      </aside>

      <main class="content">
        {case_html}
      </main>
    </div>

    <div class="footer">
      页面由 <code>build_summary_html.py</code> 从各子目录的 <code>analysis.md</code> 和 <code>answer_distribution.png</code> 生成。
    </div>
  </div>
</body>
</html>
"""


def main():
    case_paths = sorted(ROOT.glob("*/analysis.md"))
    cases = [parse_analysis(path) for path in case_paths]
    OUTPUT.write_text(build_html(cases), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
