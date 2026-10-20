"""Pure policies. DecisionGate is the only producer of gate_state."""
import hashlib
import json
from datetime import datetime, timezone
from pydantic import ValidationError
from .contracts import Health, Technical, Spares, Agency, Gate

POLICY_VERSION = 'gate-a-v1'
MODELS = {'health': Health, 'technical': Technical, 'spares': Spares, 'agency': Agency}

def now():
    return datetime.now(timezone.utc)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def assemble(bundle):
    accepted, validation, seen = [], [], set()
    for raw in bundle['records']:
        key = raw.get('source_record_key', 'UNKNOWN')
        try:
            cls = MODELS.get(raw.get('domain'))
            if cls is None:
                raise ValueError('UNKNOWN_DOMAIN')
            r = cls.model_validate(raw).model_dump(mode='json')
            identity = (r['source_record_key'], r['record_version'])
            if identity in seen:
                raise ValueError('DUPLICATE_OR_CONFLICT')
            seen.add(identity)
            accepted.append(r)
            validation.append({'key': key, 'state': 'VALIDATED', 'reason': 'CONTRACT_VALID'})
        except (ValueError, ValidationError):
            validation.append({'key': key, 'state': 'QUARANTINED', 'reason': 'INVALID_CONTRACT_OR_DUPLICATE'})
    domains = {d: [r for r in accepted if r['domain'] == d] for d in MODELS}
    h = domains['health'][0] if len(domains['health']) == 1 else None
    links = []
    if h:
        t = datetime.fromisoformat(h['event_time'])
        links = [r for r in domains['technical'] if r['approved'] and r['trusted'] and r['quality']=='GOOD' and r['evidence_class']!='PENDING' and r['asset_id'] == h['asset_id']
                 and h['component_id'] in (r['component_id'], r['alias'])
                 and datetime.fromisoformat(r['valid_from']) <= t < datetime.fromisoformat(r['valid_to'])]
    linkage = 'RESOLVED' if len(links) == 1 else 'UNRESOLVED'
    if len(links) > 1:
        linkage = 'CONFLICT'
    return {'title': bundle['title'], 'policy': bundle['policy'], 'records': accepted,
            'validation': validation, 'linkage': linkage,
            'asset_id': h['asset_id'] if h else 'UNKNOWN',
            'component_id': links[0]['component_id'] if len(links) == 1 else (h['component_id'] if h else 'UNKNOWN'),
            'configuration_id': links[0]['configuration_id'] if len(links) == 1 else 'UNKNOWN'}

def context(snapshot, at):
    policy = snapshot.get('policy')
    records = snapshot['records']
    groups = {d: [r for r in records if r['domain'] == d] for d in MODELS}
    max_age = (policy or {}).get('max_age_hours', 24) * 3600
    def current(r):
        age = (at - datetime.fromisoformat(r['event_time'])).total_seconds()
        ingest = datetime.fromisoformat(r['ingest_time'])
        return 0 <= age <= max_age and datetime.fromisoformat(r['event_time']) <= ingest <= at
    critical_invalid = (any(v['state'] != 'VALIDATED' for v in snapshot['validation']) or
                        any(len(groups[d]) != 1 for d in ('health','spares','agency')) or
                        not groups['technical'] or snapshot['linkage'] != 'RESOLVED' or
                        any(not r['trusted'] or r['quality']!='GOOD' or r['evidence_class']=='PENDING' for r in groups['health']))
    current_all = bool(records) and all(current(r) for r in records)
    trustworthy = all(r['trusted'] and r['quality'] == 'GOOD' and r['evidence_class'] != 'PENDING' for r in records)
    checks = []
    def check(name, value, evidence):
        state = 'UNKNOWN' if value is None else ('FEASIBLE' if value else 'INFEASIBLE_HARD')
        if not evidence or not all(current(r) and r['trusted'] and r['quality'] == 'GOOD' and r['evidence_class'] != 'PENDING' for r in evidence) or snapshot['linkage'] != 'RESOLVED':
            state = 'UNKNOWN'
        checks.append({'rule': name, 'state': state, 'evidence': [r['source_record_key'] for r in evidence]})
    s = groups['spares'][0] if len(groups['spares']) == 1 else None
    a = groups['agency'][0] if len(groups['agency']) == 1 else None
    check('COMPATIBLE_PART', snapshot['component_id'] in s['compatible_components'] if s else None, [s] if s else [])
    check('SERVICEABLE_STOCK', None if not s or s['quantity'] is None or s['serviceable'] is None else s['quantity'] > 0 and s['serviceable'], [s] if s else [])
    check('AGENCY_CAPABILITY', a['capability'] if a else None, [a] if a else [])
    check('BAY_CAPACITY', a['bay_capacity'] > 0 if a and a['bay_capacity'] is not None else None, [a] if a else [])
    check('MAINTENANCE_WINDOW', None if not a or not s or s['lead_hours'] is None else
          datetime.fromisoformat(a['window_end']) > at and
          max((datetime.fromisoformat(a['window_start'])-at).total_seconds(), s['lead_hours']*3600) < (datetime.fromisoformat(a['window_end'])-at).total_seconds(), [a,s] if a and s else [])
    check('APPROVAL', a['approval'] if a else None, [a] if a else [])
    states = [c['state'] for c in checks]
    feasibility = 'INFEASIBLE_HARD' if 'INFEASIBLE_HARD' in states else ('UNKNOWN' if 'UNKNOWN' in states else 'FEASIBLE')
    return {'policy_valid': policy is not None and policy.get('version') == POLICY_VERSION and isinstance(policy.get('rul_required'),bool),
            'critical_invalid': critical_invalid, 'current': current_all, 'trusted': trustworthy,
            'feasibility': {'state': feasibility, 'checks': checks},
            'rul': RULFacade.run(policy)}

class RULFacade:
    @staticmethod
    def run(policy):
        return {'status': 'PENDING' if (policy or {}).get('rul_required', True) else 'OUT_OF_SCOPE',
                'value': None, 'model_version': 'gate-b-not-validated'}

class DecisionGate:
    @staticmethod
    def decide(ctx):
        if not ctx['policy_valid']:
            return Gate.HOLD.value, ['RUL_POLICY_MISSING_OR_INVALID']
        if ctx['critical_invalid']:
            return Gate.HOLD.value, ['CRITICAL_EVIDENCE_OR_LINKAGE_UNRESOLVED']
        if ctx['feasibility']['state'] == 'INFEASIBLE_HARD':
            return Gate.BLOCK.value, [c['rule'] for c in ctx['feasibility']['checks'] if c['state'] == 'INFEASIBLE_HARD']
        if not ctx['current'] or not ctx['trusted'] or ctx['feasibility']['state'] == 'UNKNOWN':
            return Gate.HOLD.value, ['PREREQUISITE_UNKNOWN_OR_STALE']
        if ctx['rul']['status'] == 'PENDING':
            return Gate.HOLD.value, ['REQUIRED_RUL_NOT_ACCEPTED']
        return Gate.READY.value, ['ALL_GATE_A_PREREQUISITES_SATISFIED']

def rank(snapshot):
    # Frozen ascending lexicographic order; unknown urgency/consequence/lead sort last.
    hs = [r for r in snapshot['records'] if r['domain']=='health']
    h = hs[0] if len(hs)==1 else {}
    c = context(snapshot, now())
    return [int(c['critical_invalid']), {'FEASIBLE':0,'UNKNOWN':1,'INFEASIBLE_HARD':2}[c['feasibility']['state']],
            -h['urgency'] if h.get('urgency') is not None else 99,
            -h['consequence'] if h.get('consequence') is not None else 99,
            h.get('warning_lead_hours') if h.get('warning_lead_hours') is not None else 1e9,
            int(not c['trusted'] or not c['current'])]
