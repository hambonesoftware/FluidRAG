import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_JS = REPO_ROOT / "frontend" / "js"


def _run_node(script: str) -> dict:
    result = subprocess.run(
        ["node", "--input-type=module", "-"],
        input=script,
        text=True,
        capture_output=True,
        check=True,
    )
    stdout = result.stdout.strip().splitlines()
    payload = stdout[-1] if stdout else "{}"
    return json.loads(payload)


def test_pipeline_vm_poll_progress_completes():
    pipeline_vm_path = (FRONTEND_JS / "viewmodels" / "PipelineVM.js").as_uri()
    script = f"""
import {{ PipelineVM }} from '{pipeline_vm_path}';

class StubApi {{
  constructor() {{
    this.offline = false;
    this.calls = 0;
  }}
  async status(docId) {{
    this.calls += 1;
    if (this.calls === 1) {{
      return {{ doc_id: docId, pipeline_audit: {{}} }};
    }}
    return {{
      doc_id: docId,
      pipeline_audit: {{ status: 'ok', timestamp: '2024-01-01T00:00:00Z' }}
    }};
  }}
  async results(docId) {{
    if (this.calls === 1) {{
      return {{ passes: {{}}, manifest: {{ passes: {{}} }} }};
    }}
    return {{
      passes: {{
        summary: {{ answer: 'hello world', citations: [], retrieval: [] }}
      }},
      manifest: {{ passes: {{ summary: 'docs/passes/summary.json' }} }}
    }};
  }}
}}

const api = new StubApi();
const vm = new PipelineVM(api, {{ pollIntervalMs: 0 }});
const payload = await vm.pollProgress('doc-123', {{ intervalMs: 0 }});
console.log(JSON.stringify({{
  docId: vm.docId,
  passResults: vm.passResults.map(r => ({{
    name: r.name,
    answer: r.answer,
    artifactPath: r.artifactPath
  }})),
  progress: vm.progressPercent,
  status: vm.lastStatus.pipeline_audit.status,
  calls: api.calls,
  payload,
}}));
"""
    data = _run_node(script)
    assert data["docId"] == "doc-123"
    assert data["progress"] == 100
    assert data["status"] == "ok"
    assert data["calls"] >= 2
    assert data["passResults"] == [
        {
            "name": "summary",
            "answer": "hello world",
            "artifactPath": "docs/passes/summary.json",
        }
    ]


def test_results_view_download_artifact_triggers_anchor(tmp_path):
    results_view_path = (FRONTEND_JS / "views" / "ResultsView.js").as_uri()
    script = f"""
import {{ ResultsView }} from '{results_view_path}';

const body = {{
  appended: [],
  removed: [],
  appendChild(node) {{
    this.appended.push(node);
    this.lastAppended = node;
  }},
  removeChild(node) {{
    this.removed.push(node);
    this.lastRemoved = node;
  }}
}};

globalThis.document = {{
  body,
  createElement(tag) {{
    const element = {{
      tagName: tag,
      style: {{}},
      children: [],
      setAttribute() {{}},
      appendChild(child) {{ this.children.push(child); }},
    }};
    if (tag === 'a') {{
      element.click = function click() {{ this.clicked = true; }};
    }}
    return element;
  }}
}};

const root = {{
  nodes: [],
  events: [],
  appendChild(node) {{ this.nodes.push(node); }},
  dispatchEvent(evt) {{ this.events.push(evt); }},
  innerHTML: ''
}};

const api = {{
  offline: false,
  artifact: (path) => `http://localhost/pipeline/artifacts?path=${{path}}`
}};

const view = new ResultsView(root, {{ apiClient: api }});
view.downloadArtifact('doc/pass.json');
console.log(JSON.stringify({{
  href: body.lastAppended.href,
  clicked: Boolean(body.lastAppended.clicked),
  events: root.events,
  removed: body.lastRemoved === body.lastAppended
}}));
"""
    data = _run_node(script)
    assert data["href"].endswith("path=doc/pass.json")
    assert data["clicked"] is True
    assert data["removed"] is True
    assert any(evt["type"] == "artifact-download" for evt in data["events"])


def test_results_view_download_artifact_offline_dispatches_event():
    results_view_path = (FRONTEND_JS / "views" / "ResultsView.js").as_uri()
    script = f"""
import {{ ResultsView }} from '{results_view_path}';

globalThis.document = {{
  body: {{
    appendChild() {{ throw new Error('should not append in offline mode'); }},
    removeChild() {{}}
  }},
  createElement(tag) {{
    return {{ tagName: tag, style: {{}}, click() {{ this.clicked = true; }} }};
  }}
}};

const root = {{
  events: [],
  appendChild() {{}},
  dispatchEvent(evt) {{ this.events.push(evt); }},
  innerHTML: ''
}};

const api = {{ offline: true, artifact: () => 'http://example' }};
const view = new ResultsView(root, {{ apiClient: api }});
view.downloadArtifact('doc/pass.json');
console.log(JSON.stringify({{ events: root.events }}));
"""
    data = _run_node(script)
    assert any(evt["type"] == "artifact-offline" for evt in data["events"])
