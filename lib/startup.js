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
const SKILL_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/**
 * Read the leading `---` block of a SKILL.md into a Map.
 *
 * Deliberately strict and small: only single-line `key: value` pairs at the top
 * level are read, indented continuation blocks are skipped, and the first
 * occurrence of a key wins. That is all a skill manifest needs, and it keeps
 * this package free of a YAML dependency.
 */
function readFrontmatter(text) {
  if (!text.startsWith('---')) return null;
  const closing = text.indexOf('\n---', 3);
  if (closing === -1) return null;

  const fields = new Map();
  for (const line of text.slice(3, closing).split('\n')) {
    const first = line.charAt(0);
    if (line.trim() === '' || first === ' ' || first === '\t' || first === '#') continue;
    const separator = line.indexOf(':');
    if (separator < 1) continue;
    const key = line.slice(0, separator).trim();
    if (fields.has(key)) continue;
    fields.set(key, line.slice(separator + 1).trim().replace(/^(['"])(.*)\1$/, '$2'));
  }
  return fields;
}

/** Load one skill directory relative to this package, or null if unusable. */
function loadSkill(relativeDir) {
  const skillDir = join(PACKAGE_ROOT, relativeDir);
  const manifest = join(skillDir, 'SKILL.md');
  if (!existsSync(manifest) || !statSync(manifest).isFile()) return null;

  const text = readFileSync(manifest, 'utf8');
  const fields = readFrontmatter(text);
  if (!fields) return null;

  const name = fields.get('name');
  const description = fields.get('description');
  if (typeof name !== 'string' || !SKILL_NAME.test(name)) return null;
  if (typeof description !== 'string' || description.length === 0) return null;

  const bodyStart = text.indexOf('\n---', 3) + 4;
  return {
    name,
    description,
    content: text.slice(bodyStart).replace(/^\n/, ''),
    resourceBase: { kind: 'directory', path: skillDir },
  };
}

/** Optional local hint. Absent configuration produces no text at all. */
function interpreterHint() {
  const configured = (process.env.PDF2MD_PYTHON ?? '').trim();
  if (!configured) return '';
  return [
    '',
    '## Local interpreter (from PDF2MD_PYTHON)',
    '',
    `\`${configured}\``,
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
