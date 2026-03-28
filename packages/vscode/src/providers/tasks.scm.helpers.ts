export function extractPatchForFile(diff: string, filePath: string): string {
  if (!diff) {
    return "";
  }

  const normalizedFilePath = filePath.replace(/^\/+/, "");
  const sections = splitDiffSections(diff);
  for (const section of sections) {
    const match = section.match(/^diff --git a\/(.+?) b\/(.+)$/m);
    if (!match) {
      continue;
    }
    const [, oldPath, newPath] = match;
    if (oldPath === normalizedFilePath || newPath === normalizedFilePath) {
      return section.trim();
    }
  }

  return diff.trim();
}

export function splitDiffSections(diff: string): string[] {
  const lines = diff.split("\n");
  const sections: string[] = [];
  let current: string[] = [];

  for (const line of lines) {
    if (line.startsWith("diff --git ") && current.length > 0) {
      sections.push(current.join("\n"));
      current = [];
    }
    current.push(line);
  }

  if (current.length > 0) {
    sections.push(current.join("\n"));
  }

  return sections;
}
