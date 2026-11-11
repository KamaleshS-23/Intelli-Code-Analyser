package demo;

/**
 * Performance smell: string + inside loops.
 */
public class ReportGenerator {

    public String buildCSVReport(String[] rows) {
        String csv = "id,value\n";
        for (int i = 0; i < rows.length; i++) {
            csv = csv + i + "," + rows[i] + "\n";
        }
        return csv;
    }
}
