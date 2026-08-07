#include <QString>
#include <QCoreApplication>
#include <cstdio>

static bool isCustomFixed(const QString &path, const QString &dir) {
    return path == dir || path.startsWith(dir + QLatin1Char('/'));
}
static bool isCustomOld(const QString &path, const QString &dir) {
    return path.startsWith(dir);
}

int main(int argc, char *argv[]) {
    QCoreApplication app(argc, argv);

    const QString base = "/home/qet/.local/share/QElectroTech/QElectroTech";
    const QString customDir  = base + "/elements";
    const QString companyDir = base + "/elements-company";

    printf("OLD logic (should show BUG for company paths):\n");
    printf("  company root isCustom: %s  (BUG if true)\n",
           isCustomOld(companyDir, customDir) ? "TRUE [BUG]" : "false [ok]");
    printf("  company item isCustom: %s  (BUG if true)\n",
           isCustomOld(companyDir + "/foo.elmt", customDir) ? "TRUE [BUG]" : "false [ok]");
    printf("  custom  root isCustom: %s\n",
           isCustomOld(customDir, customDir) ? "true [ok]" : "FALSE [BROKEN]");
    printf("  custom  item isCustom: %s\n",
           isCustomOld(customDir + "/foo.elmt", customDir) ? "true [ok]" : "FALSE [BROKEN]");

    printf("\nFIXED logic:\n");
    bool fc_root = isCustomFixed(companyDir, customDir);
    bool fc_item = isCustomFixed(companyDir + "/foo.elmt", customDir);
    bool cu_root = isCustomFixed(customDir, customDir);
    bool cu_item = isCustomFixed(customDir + "/foo.elmt", customDir);

    printf("  company root isCustom: %s\n", fc_root ? "TRUE [FAIL]" : "false [PASS]");
    printf("  company item isCustom: %s\n", fc_item ? "TRUE [FAIL]" : "false [PASS]");
    printf("  custom  root isCustom: %s\n", cu_root ? "true [PASS]" : "FALSE [FAIL]");
    printf("  custom  item isCustom: %s\n", cu_item ? "true [PASS]" : "FALSE [FAIL]");

    bool ok = !fc_root && !fc_item && cu_root && cu_item;
    printf("\n%s\n", ok ? "ALL PASS" : "FAIL");
    return ok ? 0 : 1;
}
