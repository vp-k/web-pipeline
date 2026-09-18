"""Run a real disposable Baseline/Full lifecycle, stopping at REVIEW."""
from __future__ import annotations
import argparse, json, shutil, subprocess, sys, tempfile
from pathlib import Path

def run(command, cwd): subprocess.run(command,cwd=cwd,check=True)
def main():
    p=argparse.ArgumentParser();p.add_argument("--output",help="optional new directory for retained evidence");a=p.parse_args()
    kit=Path(__file__).resolve().parents[2]/"kit"
    with tempfile.TemporaryDirectory(prefix="web-pipeline-example-") as td:
        root=Path(td)/"project"
        run([sys.executable,"-m","web_pipeline","init","--target",str(root)],kit)
        config=json.loads((root/"pipeline.config.yaml").read_text(encoding="utf-8"))
        config["project"].update({"name":"minimal-real-check","mode":"project","ready":True,"supported_domains":["backend"]})
        config["verification"]["policy_checks"]=[]
        for profile in ("Baseline","Fast","Full","Release"): config["verification"]["requirements"]["backend"][profile]=["unit"]
        for command in config["verification"]["commands"]:
            command["enabled"]=command["id"]=="unit"
            command["argv"]=[sys.executable,"-m","unittest","test_app.py","-v"] if command["id"]=="unit" else []
        (root/"pipeline.config.yaml").write_text(json.dumps(config,indent=2)+"\n",encoding="utf-8")
        (root/"app.py").write_text("def add(a,b): return a+b\n",encoding="utf-8")
        (root/"test_app.py").write_text("import unittest\nfrom app import add\nclass T(unittest.TestCase):\n def test_add(self): self.assertEqual(3,add(1,2))\n",encoding="utf-8")
        run(["git","init"],root);run(["git","config","user.email","fixture@example.invalid"],root);run(["git","config","user.name","Pipeline Fixture"],root);run(["git","add","."],root);run(["git","commit","-m","fixture baseline"],root)
        cli=[sys.executable,"-m","web_pipeline","--root",str(root)]
        run(cli+["new","--task","EXAMPLE-1","--title","Verified addition","--tier","T1","--domains","backend","--base-ref","HEAD"],kit)
        task=root/"Docs/Work/EXAMPLE-1"
        (task/"BRIEF.md").write_text("# Verified addition\n\nScope: execute the addition unit test.\n",encoding="utf-8")
        (task/"DOR.md").write_text("# Definition of Ready\n\nBaseline command and acceptance check are configured.\n",encoding="utf-8")
        (task/"ACCEPTANCE.json").write_text(json.dumps({"criteria":[{"id":"AC-01","description":"addition returns three","checks":["unit"]}]},indent=2)+"\n",encoding="utf-8")
        planning=json.loads((task/'CLARIFICATIONS.json').read_text(encoding='utf-8'))
        findings=['Execute the local addition unit test only.', 'Call add(1, 2) and observe three.',
                  'The example has no UI, remote requests or input validation scope.',
                  'Local Python values only; no persistent data or integrations.',
                  'Disposable fixture; keep all engine approval and evidence gates.',
                  'AC-01 maps the specified result to the real unit test.']
        for entry,finding in zip(planning['analysis'],findings):
            entry.update(finding=finding,sources=[{'kind':'document','reference':'Docs/Work/EXAMPLE-1/BRIEF.md',
                                                  'excerpt':'Scope: execute the addition unit test.'}])
        (task/'CLARIFICATIONS.json').write_text(json.dumps(planning,indent=2)+'\n',encoding='utf-8')
        run(cli+["prepare","--task","EXAMPLE-1","--implementer","fixture-implementer"],kit)
        run(cli+["run","--task","EXAMPLE-1","--profile","Baseline","--run-id","example-baseline"],kit)
        run(cli+["transition","--task","EXAMPLE-1","--status","READY"],kit)
        run(cli+["transition","--task","EXAMPLE-1","--status","IN_PROGRESS"],kit)
        run(cli+["transition","--task","EXAMPLE-1","--status","VERIFYING"],kit)
        run(cli+["run","--task","EXAMPLE-1","--profile","Full","--run-id","example-full"],kit)
        run(cli+["transition","--task","EXAMPLE-1","--status","REVIEW"],kit)
        if a.output:
            output=Path(a.output).resolve()
            if kit == output or kit in output.parents: p.error("--output must be outside the kit")
            shutil.copytree(root/"Reports/Pipeline",output)
            print(f"Evidence retained at {output}")
        print("Reached REVIEW with executed evidence; DONE intentionally requires an external signed Reviewer approval.")
if __name__=="__main__": main()
