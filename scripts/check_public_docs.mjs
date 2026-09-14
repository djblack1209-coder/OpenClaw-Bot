import { existsSync, readFileSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const repository = 'https://github.com/djblack1209-coder/OpenClaw-Bot/';
export const publicFiles = [
  'README.md',
  'docs/004-architecture.md',
  'docs/005-quickstart.md',
  'docs/013-contributing.md',
  'docs/016-readme-en.md',
  'docs/017-engineering-tour.md',
  '.github/CONTRIBUTING.md',
  '.github/SECURITY.md',
  '.github/CODE_OF_CONDUCT.md',
  '.github/ISSUE_TEMPLATE/config.yml',
  'apps/project-showcase/index.html',
];

// 验证公开入口使用的行内 Markdown、HTML 资源与同仓库 main 链接。
// 不联网探测第三方站点，也不把存在性检查表述为锚点或渲染验收。
export function missingPublicTargets(root, files) {
  const missing = [];
  for (const file of files) {
    const source = resolve(root, file);
    if (!existsSync(source)) {
      missing.push(`${file}: source missing`);
      continue;
    }
    const content = readFileSync(source, 'utf8').replace(/```[^\n]*\n[\s\S]*?```/g, '');
    const targets = [
      ...Array.from(content.matchAll(/\]\(([^\s)]+)(?:\s+"[^"]*")?\)/g), (match) => match[1]),
      ...Array.from(content.matchAll(/(?:href|src)=["']([^"']+)["']/g), (match) => match[1]),
      ...Array.from(content.matchAll(/^\s*url:\s*(\S+)/gm), (match) => match[1]),
    ];
    for (const raw of new Set(targets)) {
      let target = raw;
      let base = dirname(source);
      if (target.startsWith(`${repository}blob/main/`) || target.startsWith(`${repository}tree/main/`)) {
        target = target.slice(repository.length).replace(/^(blob|tree)\/main\//, '');
        base = root;
      } else if (/^[a-z][a-z\d+.-]*:/i.test(target) || target.startsWith('//') || target.startsWith('#')) {
        continue;
      }
      try {
        target = decodeURIComponent(target.split(/[?#]/, 1)[0]);
      } catch {
        missing.push(`${file}: invalid URL ${raw}`);
        continue;
      }
      const absolute = resolve(base, target);
      const within = relative(root, absolute);
      if (isAbsolute(within) || within === '..' || within.startsWith('../') || !existsSync(absolute)) {
        missing.push(`${file}: missing local target ${raw}`);
      }
    }
  }
  return missing;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const root = fileURLToPath(new URL('../', import.meta.url));
  const missing = missingPublicTargets(root, publicFiles);
  if (missing.length) {
    console.error(missing.join('\n'));
    process.exitCode = 1;
  } else {
    console.log(`Public documentation links: ${publicFiles.length} entry files checked; local targets exist.`);
  }
}
