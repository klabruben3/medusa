"""Checkpoint namespace only; callers must authorize the owner before lookup.

The experiment uses a protected local review scope. A hosted caller must derive
owner_scope from its verified session and enforce storage/RLS; this hash is not auth.
"""
import hashlib
import json
from .fact_ledger import batch_fingerprint


def checkpoint_key(review, inputs, model, batch, *, owner_scope):
    if not isinstance(owner_scope, str) or not owner_scope:
        raise ValueError('A verified owner scope is required')
    files = {block['source_file'] for block in batch}
    payload = {'ownerScope': owner_scope, 'review': review['reference'],
        'credentialDigest': review['apiKeySha256'], 'model': model, 'request': batch_fingerprint(batch),
        'inputs': sorted((item['file'], item['sha256']) for item in inputs if item['file'] in files)}
    if {file for file, _ in payload['inputs']} != files:
        raise ValueError('Checkpoint source hashes are incomplete')
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
