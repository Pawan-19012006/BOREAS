export type SelectionKind = 'iceberg' | 'vessel' | 'risk-cell' | null;

export interface Selection {
  kind: SelectionKind;
  id: string;
}
