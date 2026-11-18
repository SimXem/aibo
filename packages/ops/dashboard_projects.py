"""Project-specific inputs to the production release and forecast job."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Dashboard:
    project: str
    web: str                   # relative to project, contains the frontend manifest
    build: tuple               # argv after the release Python; {results} and {site} are paths
    forecast: tuple            # argv after the release Python
    downloads: tuple = ()
    required: tuple = ()
    assets: tuple = ()         # (source relative to project, destination relative to site)
    block: str = ''            # survey payload used to validate publications
    assembled: str = ''        # optional preassembled frontend relative to project


AIRO_FILES = ('forecasts.csv', 'rationales.csv', 'debriefs.csv', 'redlines-data.zip')
DASHBOARDS = {
    # AIRO has its own accrual, eligibility and publication scripts.
    'airo': Dashboard('dashboards/airo', 'web/demo', (), (), AIRO_FILES,
                      ('forecasts.csv', 'rationales.csv', 'redlines-data.zip'),
                      (('web/img', 'web/img'), ('web/fonts', 'web/fonts')), assembled='index.html'),
    'eeai': Dashboard('dashboards/eeai', 'eeai/web',
                      ('-m', 'eeai', 'build', '--publication', '--runs', '{results}', '--site', '{site}'),
                      ('-m', 'eeai', 'run', '--out', '{results}'),
                      ('eeai-data.zip',), ('eeai-data.zip',),
                      (('eeai/web/img', 'web/img'), ('eeai/web/fonts', 'web/fonts')), block='EEAI'),
    'rsi': Dashboard('dashboards/rsi', 'rsi_dashboard/web',
                     ('-m', 'rsi_dashboard', '--publication', '--results', '{results}', '--site', '{site}'),
                     ('-m', 'rsi_dashboard.run', '--condition', 'both', '--out', '{results}'), block='SURVEY'),
}
