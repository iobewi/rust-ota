#!/usr/bin/env python3
"""Audit issue #14 against its immutable baseline; --write-report regenerates the hash inventory.
No builds, downloads or hardware actions. Requires the baseline Git commit to be present.
"""
import pathlib,json,hashlib,subprocess,tomllib,re,os
root=pathlib.Path(__file__).resolve().parents[1]
os.chdir(root)
base='ec6035b1270e1ee3a5f282d6a1f2ba15a0ee015e'
prefixes={'common/firmware/':'common/','arch/esp32/firmware/':'arch/esp32/','examples/firmware/':'examples/','docs/firmware/':'docs/'}
def mapped(path):
    for a,c in prefixes.items():
        if path.startswith(a):return c+path[len(a):]
    return path
files=subprocess.check_output(['git','ls-tree','-r','--name-only',base],text=True).splitlines()
original={p:subprocess.check_output(['git','show',base+':'+p]) for p in files}
b={'base':base,'files':{p:{'new':mapped(p),'sha256':hashlib.sha256(data).hexdigest()} for p,data in original.items()},'manifests':{p:tomllib.loads(data.decode()) for p,data in original.items() if p.endswith('Cargo.toml')}}
rows=[];exceptions=[]
for old,item in b['files'].items():
    new=item['new'];data=pathlib.Path(new).read_bytes()
    if old.endswith('.rs'):
        before=subprocess.check_output(['git','show',b['base']+':'+old]);after=data
        if after!=before:
            exceptions.append(new)
            expected=before.decode()
            for prefix in ['common/firmware/','arch/esp32/firmware/','examples/firmware/','docs/firmware/']:
                expected=expected.replace(prefix,prefix.replace('firmware/',''))
            expected=expected.replace('{dir}/../../../arch/esp32/boot/linker','{dir}/../../arch/esp32/boot/linker').replace('../../../../common/component/sdk/ld/','../../../common/component/sdk/ld/').replace('../../../../../examples/ota-system/','../../../../examples/ota-system/').replace('/../../web/firmware/esp32c3/app.bin','/../web/firmware/esp32c3/app.bin')
            assert re.sub(r'\s+','',expected)==re.sub(r'\s+','',after.decode()),'Unexpected Rust edit: '+new
        rows.append({'before':old,'after':new,'sha256_before':item['sha256'],'sha256_after':hashlib.sha256(after).hexdigest(),'byte_identical':before==after})
    if old.endswith(('.ld','.x','.bin','.hex','.csv')):assert hashlib.sha256(data).hexdigest()==item['sha256'],new
# Compare manifest contracts excluding path values (rewired local references).
def strip_paths(obj):
    if isinstance(obj,dict):return {k:strip_paths(v) for k,v in obj.items() if k!='path'}
    if isinstance(obj,list):return [strip_paths(v) for v in obj]
    return obj
for old,manifest in b['manifests'].items():
    new=b['files'][old]['new'];current=tomllib.loads(pathlib.Path(new).read_text())
    if old=='Cargo.toml':
        expected=dict(manifest);expected['workspace']=dict(manifest['workspace']);expected['workspace']['members']=[b['files'].get(v+'/Cargo.toml',{}).get('new',v+'/Cargo.toml').removesuffix('/Cargo.toml') for v in manifest['workspace']['members']]
    else:expected=manifest
    assert strip_paths(expected)==strip_paths(current),new
    def visit(obj):
        if isinstance(obj,dict):
            for k,v in obj.items():
                if k=='path':
                    resolved=(pathlib.Path(new).parent/v).resolve();assert resolved.is_relative_to(root) and resolved.exists(),(new,v)
                else:visit(v)
        elif isinstance(obj,list):
            for v in obj:visit(v)
    visit(current)
assert not any(pathlib.Path(p).exists() for p in ['common/firmware','arch/esp32/firmware','examples/firmware','docs/firmware'])
# Existing local Markdown links must still resolve after mapping their source/target.
new_broken=[];existing_broken=[]
for old,item in b['files'].items():
    if not old.endswith('.md') or old.endswith('porting-audit-s0.md'):continue
    before=subprocess.check_output(['git','show',b['base']+':'+old]).decode()
    after=pathlib.Path(item['new']).read_text()
    def links(text):return [x.split('#')[0] for x in re.findall(r'\]\(([^)\s]+)\)',text) if not x.startswith(('#','/','mailto:')) and '://' not in x]
    for target in links(after):
        if not target:continue
        if not (pathlib.Path(item['new']).parent/target).exists():new_broken.append((item['new'],target))
    for target in links(before):
        orig=os.path.normpath(str(pathlib.PurePosixPath(old).parent/target))
        if orig not in b['files'] and not any(k.startswith(orig.rstrip('/')+'/') for k in b['files']):existing_broken.append((old,target))
assert not new_broken,new_broken
result={'baseline':b['base'],'rust_files':len(rows),'byte_identical':sum(r['byte_identical'] for r in rows),'exceptions':exceptions,'files':rows}
report=pathlib.Path('docs/tree-reorganization-hashes.json')
if '--write-report' in __import__('sys').argv:
    report.write_text(json.dumps(result,indent=2)+'\n')
else:
    assert json.loads(report.read_text())==result,'recorded hash report differs from current tree'
print('Rust:',len(rows),'files;',result['byte_identical'],'byte-identical;',len(exceptions),'path/comment exceptions')
print('Manifest contracts unchanged; local paths exist inside repo; linkers/fixtures/tables byte-identical')
print('Existing broken Markdown links:',existing_broken,'remaining:',new_broken)
