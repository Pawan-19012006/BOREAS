// Real distillation/quantization measurements (BOREAS design doc §5.1).
// See boreas-core/README.md and boreas-core/scripts/run_edge_distillation.py.

import { useEffect, useState } from 'react';
import { getEdgeReport, type EdgeConfigReport, type EdgeReportResponse } from '../../services/boreasApi';

function ConfigCard({ title, report }: { title: string; report: EdgeConfigReport }) {
  return (
    <div className="edge-config-card">
      <h4>{title}</h4>
      <div className="inspector-field-grid">
        <div className="inspector-field"><label>Params</label><span>{report.student_param_count.toLocaleString()}</span></div>
        <div className="inspector-field"><label>Compression</label><span>{report.compression_ratio.toFixed(0)}x</span></div>
        <div className="inspector-field"><label>Size (fp32→int8)</label><span>{report.fp32_size_kb.toFixed(1)}→{report.int8_size_kb.toFixed(1)} KB</span></div>
        <div className="inspector-field"><label>Size Reduction</label><span>{report.size_reduction_pct.toFixed(0)}%</span></div>
        <div className="inspector-field"><label>Latency (fp32→int8)</label><span>{report.fp32_latency_ms.toFixed(2)}→{report.int8_latency_ms.toFixed(2)} ms</span></div>
        <div className="inspector-field"><label>Student vs. Teacher MSE</label><span>{report.student_vs_teacher_mse.toFixed(4)}</span></div>
      </div>
    </div>
  );
}

export const EdgeAIPanel = () => {
  const [report, setReport] = useState<EdgeReportResponse | null>(null);

  useEffect(() => {
    getEdgeReport().then(setReport);
  }, []);

  return (
    <div className="panel-content">
      <span className="panel-label">EDGE-DISTILLED FORECAST MODEL</span>
      <p className="inspector-rationale">
        A small student network distilled from the real trained 11M-parameter teacher, then
        quantized to INT8 — sized for offline, low-bandwidth edge deployment.
      </p>

      {!report && <p className="nav-error">Loading edge report…</p>}
      {report && !report.available && (
        <p className="nav-error">
          No edge report yet — run boreas-core/scripts/run_edge_distillation.py.
        </p>
      )}
      {report?.tiny && <ConfigCard title="Tiny (6K params)" report={report.tiny} />}
      {report?.edge_target && <ConfigCard title="Edge-Target (170K params)" report={report.edge_target} />}

      <p className="inspector-rationale">
        Honest caveat: dynamic INT8 quantization shrinks model size ({report?.edge_target?.size_reduction_pct.toFixed(0) ?? '~74'}%
        smaller) but does not reduce CPU latency without static/calibrated quantization or real
        ARM/Jetson-class INT8 execution hardware — reported as measured, not oversold.
      </p>
    </div>
  );
};

export default EdgeAIPanel;
