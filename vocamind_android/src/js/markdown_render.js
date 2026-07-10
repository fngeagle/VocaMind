/** 轻量 Markdown 渲染（无外部依赖，适配移动端 WebView）。 */

export function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inlineFormat(text) {
  let s = escapeHtml(text);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return s;
}

function isHorizontalRule(line) {
  return /^(\*{3,}|-{3,}|_{3,})\s*$/.test(line.trim());
}

function isTableRow(line) {
  const trimmed = line.trim();
  if (!trimmed.includes("|")) return false;
  if (isHorizontalRule(trimmed)) return false;
  return trimmed.startsWith("|") || trimmed.endsWith("|") || trimmed.split("|").length >= 2;
}

function isTableSeparator(line) {
  const trimmed = line.trim();
  if (!trimmed.includes("|") && !trimmed.includes("-")) return false;
  return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(trimmed);
}

function parseTableRow(line) {
  let trimmed = line.trim();
  if (trimmed.startsWith("|")) trimmed = trimmed.slice(1);
  if (trimmed.endsWith("|")) trimmed = trimmed.slice(0, -1);
  return trimmed.split("|").map((cell) => cell.trim());
}

function renderTable(headerCells, bodyRows) {
  const head = headerCells
    .map((cell) => `<th>${inlineFormat(cell)}</th>`)
    .join("");
  const body = bodyRows
    .map(
      (row) =>
        `<tr>${row.map((cell) => `<td>${inlineFormat(cell)}</td>`).join("")}</tr>`,
    )
    .join("");
  return `<div class="md-table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

export function renderMarkdown(source) {
  const lines = String(source).replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let inCode = false;
  let listType = null;
  let i = 0;

  const closeList = () => {
    if (listType) {
      out.push(listType === "ul" ? "</ul>" : "</ol>");
      listType = null;
    }
  };

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("```")) {
      closeList();
      if (!inCode) {
        out.push("<pre><code>");
        inCode = true;
      } else {
        out.push("</code></pre>");
        inCode = false;
      }
      i += 1;
      continue;
    }
    if (inCode) {
      out.push(escapeHtml(line), "\n");
      i += 1;
      continue;
    }

    if (
      isTableRow(line) &&
      i + 1 < lines.length &&
      isTableSeparator(lines[i + 1])
    ) {
      closeList();
      const headerCells = parseTableRow(line);
      i += 2;
      const bodyRows = [];
      while (i < lines.length && isTableRow(lines[i]) && !isTableSeparator(lines[i])) {
        bodyRows.push(parseTableRow(lines[i]));
        i += 1;
      }
      out.push(renderTable(headerCells, bodyRows));
      continue;
    }

    if (isHorizontalRule(line)) {
      closeList();
      out.push("<hr />");
      i += 1;
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      closeList();
      const level = heading[1].length;
      out.push(`<h${level}>${inlineFormat(heading[2])}</h${level}>`);
      i += 1;
      continue;
    }

    const ul = line.match(/^[-*+]\s+(.*)$/);
    if (ul) {
      if (listType !== "ul") {
        closeList();
        out.push("<ul>");
        listType = "ul";
      }
      out.push(`<li>${inlineFormat(ul[1])}</li>`);
      i += 1;
      continue;
    }

    const ol = line.match(/^\d+\.\s+(.*)$/);
    if (ol) {
      if (listType !== "ol") {
        closeList();
        out.push("<ol>");
        listType = "ol";
      }
      out.push(`<li>${inlineFormat(ol[1])}</li>`);
      i += 1;
      continue;
    }

    if (!line.trim()) {
      closeList();
      i += 1;
      continue;
    }

    closeList();
    out.push(`<p>${inlineFormat(line)}</p>`);
    i += 1;
  }

  closeList();
  if (inCode) {
    out.push("</code></pre>");
  }
  return out.join("\n");
}
