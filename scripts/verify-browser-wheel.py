"""Install wheel in an isolated venv and run the real headless browser MCP contract."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
import zipfile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('wheel',type=Path)
parser.add_argument('--evidence',type=Path,required=True)
args=parser.parse_args()
wheel=args.wheel.resolve(strict=True); evidence=args.evidence.resolve(); evidence.mkdir(parents=True,exist_ok=True)
project=Path(__file__).resolve().parents[1]
resources=('browser-worker.mjs','browser-session.mjs','browser-background.mjs')
with zipfile.ZipFile(wheel) as archive:
    for name in resources:
        if archive.read('window_pilot/_resources/'+name)!=(project/'scripts'/name).read_bytes():
            raise RuntimeError('wheel resource differs from reviewed source: '+name)
clean_env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME'}}
with tempfile.TemporaryDirectory(prefix='window-pilot-browser-wheel-') as temporary:
    root=Path(temporary); environment=root/'env'; venv.EnvBuilder(with_pip=True).create(environment)
    python=environment/'Scripts/python.exe'
    subprocess.run([str(python),'-m','pip','install','--no-index','--disable-pip-version-check',str(wheel)],check=True,cwd=root,env=clean_env,timeout=90)
    code='''import sys,os,pathlib,unittest
sys.path.insert(0,sys.argv[1])
import window_pilot
from window_pilot.resources import runtime_script
assert pathlib.Path(window_pilot.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()), window_pilot.__file__
for name in ('browser-worker.mjs','browser-session.mjs','browser-background.mjs'):
    assert runtime_script(name).parent.name == '_resources', runtime_script(name)
os.environ['WINDOW_PILOT_BROWSER_TESTS']='1'
import test_browser_mcp
# All browser calls below import only the installed package; tests are external clients.
test_browser_mcp.EVIDENCE=pathlib.Path(sys.argv[2])
suite=unittest.defaultTestLoader.loadTestsFromModule(test_browser_mcp)
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
'''
    result=subprocess.run([str(python),'-I','-c',code,str(project/'tests'),str(evidence/'real-browser')],cwd=root,env=clean_env,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=120)
    (evidence/'installed-browser-output.txt').write_text(result.stdout+result.stderr,encoding='utf8')
    summary={'wheel':str(wheel),'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'resource_bytes_match':list(resources),'installed_real_browser_tests_exit':result.returncode}
    (evidence/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    print(json.dumps(summary),flush=True)
    if result.returncode: print(result.stdout+result.stderr);sys.exit(result.returncode)
