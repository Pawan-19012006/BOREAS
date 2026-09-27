export type SelectionKind = 'iceberg' | 'vessel' | 'risk-cell' | 'weather' | null;

export interface Selection {
  kind: SelectionKind;
  id: string;
}
