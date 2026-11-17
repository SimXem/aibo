"""Stage: draw the sample (D5, D6) by hash-ranking; compute inclusion probabilities.

Eligible = frame units minus literature finds (S-dependent, logged).
1. Guaranteed: the n_guaranteed solved units with the smallest sha256(seed|rules|guaranteed|unit).
2. Random: n_total - n_guaranteed units from the rest of the eligible set, allocated to strata in
   proportion to stratum size (largest remainder, ties by stratum name), smallest
   sha256(seed|rules|random|unit) within each stratum.
"""
from fractions import Fraction

from .common import hash_rank

SAMPLE_FIELDS = ['unit_id', 'code', 'role', 'stratum', 'collection', 'display_name', 'solved', 'solve_date',
                 'outcome_type', 'incl_prob', 'rank_key']


def _largest_remainder(sizes, n):
    total = sum(sizes.values())
    if total == 0:
        return {k: 0 for k in sizes}
    quotas = {k: Fraction(v * n, total) for k, v in sizes.items()}
    alloc = {k: int(q) for k, q in quotas.items()}
    left = n - sum(alloc.values())
    for k in sorted(sizes, key=lambda k: (-(quotas[k] - alloc[k]), k))[:left]:
        alloc[k] += 1
    return alloc


def draw(units, outcomes, wave, rules):
    seed = f"{wave['seed']}|{rules['version']}"
    out = {o['unit_id']: o for o in outcomes}
    eligible = [u for u in units if not int(out[u['unit_id']]['literature_find'])]
    solved = [u for u in eligible if int(out[u['unit_id']]['solved'])]
    n_g = min(wave['n_guaranteed_solved'], len(solved))
    log = {'n_frame': len(units), 'n_eligible': len(eligible), 'n_solved_pool': len(solved),
           'n_guaranteed': n_g, 'guaranteed_shortfall': wave['n_guaranteed_solved'] - n_g}

    g_rank = sorted(solved, key=lambda u: hash_rank(seed, f"guaranteed|{u['unit_id']}"))
    guaranteed = g_rank[:n_g]
    gid = {u['unit_id'] for u in guaranteed}
    rest = [u for u in eligible if u['unit_id'] not in gid]
    n_r = wave['n_total'] - n_g
    sizes = {}
    for u in rest:
        sizes[u['stratum']] = sizes.get(u['stratum'], 0) + 1
    alloc = _largest_remainder(sizes, n_r)
    log['strata_sizes'] = dict(sorted(sizes.items()))
    log['strata_alloc'] = dict(sorted(alloc.items()))

    picked = []
    for s in sorted(alloc):
        members = sorted((u for u in rest if u['stratum'] == s), key=lambda u: hash_rank(seed, f"random|{u['unit_id']}"))
        picked += members[:alloc[s]]

    # Inclusion probabilities. Guaranteed draw: n_g / |solved|. Random draw: alloc_h / size_h, where size_h
    # is conditional on the realised guaranteed draw (approximation, labelled as such in the lock).
    p_g = Fraction(n_g, len(solved)) if solved else Fraction(0)
    rows = []
    for role, lst in (('guaranteed', guaranteed), ('random', picked)):
        for u in lst:
            o = out[u['unit_id']]
            p_r = Fraction(alloc[u['stratum']], sizes[u['stratum']]) if sizes.get(u['stratum']) else Fraction(0)
            p = p_g + (1 - p_g) * p_r if int(o['solved']) else p_r
            rows.append({'unit_id': u['unit_id'], 'code': 'P' + hash_rank(seed, f"code|{u['unit_id']}")[:5].upper(),
                         'role': role, 'stratum': u['stratum'], 'collection': u['collection'],
                         'display_name': u['display_name'], 'solved': o['solved'], 'solve_date': o.get('solve_date', ''),
                         'outcome_type': o.get('outcome_type', ''), 'incl_prob': f'{float(p):.6f}',
                         'rank_key': hash_rank(seed, f"{'guaranteed' if role == 'guaranteed' else 'random'}|{u['unit_id']}")[:16]})
    if len({r['code'] for r in rows}) != len(rows):
        raise RuntimeError('item code collision; change seed')
    rows.sort(key=lambda r: r['unit_id'])
    log['n_sampled'] = len(rows)
    log['n_sampled_solved'] = sum(int(r['solved']) for r in rows)
    return rows, log
