/** "Download CSV" for a chart's series.
 * A thin styled wrapper over `downloadCsv`; each lens hands it that chart's columns. */

import { Button } from "@/components/ui/button";
import { type CsvColumn, downloadCsv } from "../../lib/downloadCsv";
import { useT } from "../../lib/i18n";

export function CsvButton({
  filename,
  columns,
}: {
  filename: string;
  columns: readonly CsvColumn[];
}) {
  const t = useT();
  return (
    <Button
      type="button"
      onClick={() => downloadCsv(filename, columns)}
      variant="outline"
      size="sm"
    >
      {t("plan.csv.download")}
    </Button>
  );
}
