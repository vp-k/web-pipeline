"""Offline human-operated Ed25519 signer. It never creates or prints private keys."""
import argparse, base64, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web_pipeline.common import PipelineError, validate_schema
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def main():
    p=argparse.ArgumentParser(description="Sign a reviewed pipeline approval payload")
    p.add_argument("--payload",required=True,help="reviewed payload JSON")
    p.add_argument("--private-key",required=True,help="existing external PEM or base64 raw Ed25519 key")
    p.add_argument("--output",required=True,help="new signed envelope; must not exist")
    a=p.parse_args(); payload=json.loads(Path(a.payload).read_text(encoding="utf-8"))
    required={"task_id","revision","fingerprint","phase","role","identity","approved_utc","expires_utc","outcome","scope","conditions"}
    missing=required-set(payload)
    if missing: p.error("payload missing: "+", ".join(sorted(missing)))
    if payload["phase"] not in {"design","review","release","exception"} or payload["outcome"]!="APPROVED": p.error("invalid phase/outcome")
    if payload["phase"] in {"review","release"} and not {"tree_digest","run_id","run_digest"}.issubset(payload): p.error("review/release requires tree_digest, run_id and run_digest")
    if payload["phase"]=="exception" and not {"check_id","reason"}.issubset(payload): p.error("exception requires check_id and reason")
    try:
        validate_schema(Path(__file__).resolve().parents[1], 'exception' if payload['phase'] == 'exception' else 'approval',
                        {'payload': payload, 'signature': 'pending-human-signature'})
    except PipelineError as exc:
        p.error(str(exc))
    key_path=Path(a.private_key).expanduser().resolve(); project=Path(__file__).resolve().parents[1]
    try: key_path.relative_to(project)
    except ValueError: pass
    else: p.error("private key must be outside the project")
    key_data=key_path.read_bytes()
    try: key=serialization.load_pem_private_key(key_data,password=None)
    except ValueError: key=Ed25519PrivateKey.from_private_bytes(base64.b64decode(key_data.strip(),validate=True))
    if not isinstance(key,Ed25519PrivateKey): p.error("private key is not Ed25519")
    message=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    envelope={"payload":payload,"signature":base64.b64encode(key.sign(message)).decode("ascii")}
    with Path(a.output).open("x",encoding="utf-8",newline="\n") as stream: json.dump(envelope,stream,indent=2,ensure_ascii=False);stream.write("\n")
    print(f"signed {payload['phase']} record written to {a.output}")
if __name__=="__main__": main()
