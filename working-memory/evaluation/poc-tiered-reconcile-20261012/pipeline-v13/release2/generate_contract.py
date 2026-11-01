"""Generate synthetic expected request bytes from the prod2 modules, offline."""
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from local_support import ROOT,PROD,configure,sources

def main():
    configure()
    from importlib import import_module
    with sources():
        check=import_module('offline_check')  # overlay precedes CLI wrapper
        schema=import_module('hybrid_schema');pipeline=import_module('hybrid_pipeline')
        compact=import_module('compact_reconcile');provider=import_module('openai_provider')
        with sources(before=True):
            old_schema=check.load('_prod2_schema',PROD/'hybrid_schema.py')
            with patch.dict(sys.modules,{'hybrid_schema':old_schema}):
                old_compact=check.load('_prod2_compact',PROD/'compact_reconcile.py')
                old_pipeline=check.load('_prod2_pipeline',PROD/'hybrid_pipeline.py')
            old_provider=check.load('_prod2_provider',PROD/'openai_provider.py')
            with patch.dict(sys.modules,{'hybrid_pipeline':old_pipeline}), patch.dict('os.environ',{'DASHBOARD_DELTA_OUTPUT':'0','DASHBOARD_HOTSET_FILTER':'0','DASHBOARD_SERVICE_TIER':'default'}):
                baseline=check.contract(old_compact,old_schema,old_provider)
        import processor,canonical_worker
        processor.PROMPT_VERSION='v11'
        version=canonical_worker.pipeline_version(check.MODEL)
        if version!=check.independent_version(ROOT/'overlay'):raise ValueError('Version mismatch')
        value={'reference':'prod2 Python modules; missing evaluation assets read from working-memory/evaluation',
               'pipeline_version':version,'contract':baseline}
        (ROOT/'overlay/default_contract.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print('default_contract 1')

if __name__=='__main__':main()
