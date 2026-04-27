# Fixture: install-no-migrated

Minimal module source tree used by `test/test-installer-no-migrated.js` (Story 2.1 AC 3).

## Purpose

Proves that modules with **zero** migrated skills (no files matching the basename-match
detection rule) follow the verbatim-copy path unchanged: the compile-phase task is skipped,
Python is never invoked, and no `bmad.lock` or compiled `SKILL.md` is written by the engine.

## Contents

```
source/
  module.yaml          — module descriptor (code: no-migrated-fixture)
  plain-skill/
    SKILL.md           — verbatim skill (no *.template.md sibling)
```

## Detection rule (R3-A1)

A directory `<dir>/` is a migrated skill iff it contains `<dir>.template.md` or
`<dir>.<ide>.template.md` for `ide ∈ KNOWN_IDES`. `plain-skill/` has no such file,
so `hasMigratedSkillsInScope` returns `false`.

## Regenerating the golden hash

If fixture source files are intentionally changed, regenerate the golden hash with:

```sh
node -e "
const crypto=require('crypto'),fs=require('fs'),path=require('path');
function hashDir(dir){
  const h=crypto.createHash('sha256');
  function w(d){
    const items=fs.readdirSync(d).sort();
    for(const i of items){
      const f=path.join(d,i),rel=path.relative(dir,f).split(path.sep).join('/');
      const s=fs.statSync(f);
      if(s.isDirectory())w(f);
      else{h.update(rel+'\\n');h.update(fs.readFileSync(f));}
    }
  }
  w(dir);
  return h.digest('hex');
}
console.log(hashDir('test/fixtures/install-no-migrated/source'));
"
```

Then update `FIXTURE_GOLDEN_HASH` in `test/test-installer-no-migrated.js`.
