#!/usr/bin/env python3
import yaml, json, urllib.request, sys
from pathlib import Path
repo_root = Path(__file__).resolve().parent.parent
cfg_path = repo_root / 'development' / 'vendor-libraries.yaml'
with open(cfg_path,'r',encoding='utf-8') as f:
    cfg = yaml.safe_load(f)
libs = cfg.get('libraries',[])
mapping = {
  'tailwind': [('npm','tailwindcss')],
  'htmx': [('npm','htmx.org')],
  'jquery': [('npm','jquery')],
  'leaflet': [('npm','leaflet')],
  'chart': [('npm','chart.js')],
  'datatables': [('npm','datatables.net'),('npm','datatables.net-buttons'),('npm','datatables.net-colreorder')],
  'select2': [('npm','select2')],
  'daterangepicker': [('npm','daterangepicker')],
  'moment': [('npm','moment')],
  'jszip': [('npm','jszip')],
  'sortable': [('npm','sortablejs')],
  'html2canvas': [('npm','html2canvas')],
  'htmx-ext-sse': [('npm','htmx-ext-sse')],
  'chartjs': [('npm','chart.js')],
  'chartjs-adapter-date-fns': [('npm','chartjs-adapter-date-fns')],
  'chartjs-adapter-moment': [('npm','chartjs-adapter-moment')],
}

def npm_latest(pkg):
    url = f'https://registry.npmjs.org/{pkg}'
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
            latest = data.get('dist-tags',{}).get('latest')
            return latest
    except Exception:
        return None

results = []
for lib in libs:
    lib_id = lib.get('id')
    if not lib_id:
        continue
    lib_id_l = lib_id.lower()
    version = lib.get('version') or lib.get('versions')
    reported = None
    if isinstance(version, str):
        reported = version
    elif isinstance(version, dict):
        reported = version
    if lib_id_l == 'chart':
        versions = lib.get('versions',{})
        reported = versions
    checks = mapping.get(lib_id_l)
    if not checks:
        checks = [('npm', lib_id_l)]
    for check in checks:
        kind, name = check
        if kind=='npm':
            latest = npm_latest(name)
            if not latest:
                results.append((lib_id, name, reported, 'error'))
            else:
                rep = None
                if isinstance(reported, dict):
                    if name=='chart.js':
                        rep = reported.get('chartjs')
                    elif name=='chartjs-adapter-moment':
                        rep = reported.get('moment')
                    elif name=='chartjs-adapter-date-fns':
                        rep = reported.get('date_fns')
                else:
                    rep = reported
                results.append((lib_id, name, rep, latest))

upgrades = []
for lib_id,name,rep,latest in results:
    if latest=='error':
        print(f'{lib_id}: failed to query {name}')
        continue
    if rep is None:
        continue
    if isinstance(rep, str) and rep.strip().lower()!=str(latest).strip().lower():
        upgrades.append((lib_id,name,rep,latest))

if not upgrades:
    print('No updates detected for mapped libraries (npm registry).')
else:
    print('Libraries with newer versions available:')
    for lib_id,name,rep,latest in upgrades:
        print(f'  {lib_id} -> package {name}: configured={rep} latest={latest}')
