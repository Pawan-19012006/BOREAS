// Display formatting for backend enum values.
//
// boreas-core returns its labels and levels in upper case, which is right for
// an API and wrong for an interface: a wall of capitals is harder to scan and
// reads as shouting. These helpers change presentation only -- the underlying
// values are never altered, and are still shown verbatim in provenance lines.

/** "LOW-RISK ALTERNATIVE" -> "Low-risk alternative" */
export function sentenceCase(value: string): string {
  const lower = value.toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

/** Risk and passability levels, e.g. "VERY LOW" -> "Very low". */
export const levelLabel = sentenceCase;

/** Iceberg classification, e.g. "INTERSECTING" -> "Intersecting". */
export const classificationLabel = sentenceCase;
