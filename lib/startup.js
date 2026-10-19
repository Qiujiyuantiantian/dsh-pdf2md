// dsh-pdf2md — startup plugin.
//
// Registers the `pdf2md` skill into ctx.skills. The skill body is read from
// this package's own skills/pdf2md/ directory and carries a directory
// resourceBase, so references/quality.md and scripts/pdf2md.py resolve against
// the bundled files.
//
// Nothing machine-specific is baked in: the skill explains how to locate a
// usable Python interpreter at run time. The one optional local hint is the
// PDF2MD_PYTHON environment variable — when set, its value is surfaced in the
// skill body so the agent does not have to guess. Unset means no hint.
//
// Dependency-free by design (no runtime imports beyond node:fs/path/url).
import { readFileSync, existsSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const PACKAGE_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SKILL_REL = 'skills/pdf2md';

const NAME_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

/** Minimal frontmatter reader: single-line `key: value`, nested blocks skipped. */
function parseFrontmatter(text) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text);
  if (!match) return null;
  const fields = {};
  for (const line of match[1].split(/\r?\n/)) {
    if (!line || /^\s/.test(line) || line.trim().startsWith('#')) continue;
    const idx = line.indexOf(':');
    if (idx <= 0) continue;
    const key = line.slice(0, idx).trim();
    if (fields[key] !== undefined) continue;
    let value = line.slice(idx + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    fields[key] = value;
  }
  return fields;
}

function loadSkill(rel) {
  const skillDir = join(PACKAGE_ROOT, rel);
  const file = join(skillDir, 'SKILL.md');
  if (!existsSync(file) || !statSync(file).isFile()) return null;
  const text = readFileSync(file, 'utf8');
  const fm = parseFrontmatter(text);
  if (!fm) return null;
  const { name, description } = fm;
  if (typeof name !== 'string' || !NAME_RE.test(name)) return null;
  if (typeof description !== 'string' || description.length === 0) return null;
  const content = text.slice(text.indexOf('---', 3) + 3).replace(/^\r?\n/, '');
  return { name, description, content, resourceBase: { kind: 'directory', path: skillDir } };
}

/** Optional local hint. Absent configuration produces no text at all. */
function interpreterHint() {
  const configured = process.env.PDF2MD_PYTHON;
  if (!configured || !configured.trim()) return '';
  return [
    '',
    '## Local interpreter (from PDF2MD_PYTHON)',
    '',
    '`' + configured.trim() + '`',
    '',
    'Use this interpreter for `scripts/pdf2md.py` without searching. Verify it',
    'with `doctor` before the first conversion in a session.',
    '',
    '---',
    '',
  ].join('\n');
}

export default function apply(ctx) {
  if (!ctx?.skills) {
    console.warn('[dsh-pdf2md] ctx.skills unavailable — skill not registered');
    return;
  }
  const skill = loadSkill(SKILL_REL);
  if (!skill) {
    console.warn(`[dsh-pdf2md] failed to load ${SKILL_REL}/SKILL.md`);
    return;
  }
  ctx.skills.register({
    ...skill,
    content: interpreterHint() + skill.content,
    source: 'runtime',
  });
  console.log(`[dsh-pdf2md] registered skill ${skill.name}`);
}
