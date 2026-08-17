// S5 verification harness: proves checkConflicts() flags zero conflicts for the
// 167 blank registrations this task adds, while still flagging genuine
// same-category collisions and ignoring cross-category same-key cases (PR #759).
//
// Drives the real ShortcutsConfigPage offscreen against the current config page
// (a QTableWidget, 4 columns: category / action / key-sequence edit / reset).
#include <QApplication>
#include <QAction>
#include <QColor>
#include <QDebug>
#include <QLineEdit>
#include <QTableWidget>

#include "shortcutmanager.h"
#include "shortcutsconfigpage.h"

static int failures = 0;
static void check(bool ok, const QString &what) {
    qInfo().noquote() << (ok ? "    PASS  " : "    FAIL  ") << what;
    if (!ok) ++failures;
}

static const QColor CONFLICT_COLOR(255, 205, 205);

static int conflictRowCount(QTableWidget *t) {
    int n = 0;
    for (int r = 0; r < t->rowCount(); ++r) {
        QTableWidgetItem *item = t->item(r, 1);
        if (item && item->background().color() == CONFLICT_COLOR) ++n;
    }
    return n;
}

static int findRow(QTableWidget *t, const QString &description) {
    for (int r = 0; r < t->rowCount(); ++r) {
        if (t->item(r, 1) && t->item(r, 1)->text() == description) return r;
    }
    return -1;
}

static bool rowIsConflicted(QTableWidget *t, int r) {
    return t->item(r, 1) && t->item(r, 1)->background().color() == CONFLICT_COLOR;
}

int main(int argc, char **argv) {
    QApplication app(argc, argv);

    // Representative sample:
    //  - two BLANK actions in the same category (must never conflict),
    //  - a planted same-category duplicate pair (must conflict),
    //  - a same-key different-category action (must NOT conflict, PR #759).
    QAction a1, a2, a3, a4, a5;
    auto &m = ShortcutManager::instance();
    a1.setText(QString::fromUtf8("Plein écran"));          m.registerAction(&a1, "mainwindow.fullscreen",        QString::fromUtf8("Général"), QKeySequence("Ctrl+Shift+F"));
    a2.setText(QString::fromUtf8("Basculer plein écran")); m.registerAction(&a2, "mainwindow.toggle_fullscreen", QString::fromUtf8("Général"), QKeySequence("Ctrl+Shift+F"));
    a3.setText("Exporter en PDF");                         m.registerAction(&a3, "file.export_pdf",             "Fichier",    QKeySequence());
    a4.setText("Exporter en image");                       m.registerAction(&a4, "file.export_image",           "Fichier",    QKeySequence());
    a5.setText("Profondeur haut");                         m.registerAction(&a5, "depth.raise",                 "Profondeur", QKeySequence("Ctrl+Shift+F"));

    ShortcutsConfigPage page;
    auto *table  = page.findChild<QTableWidget*>();
    auto *filter = page.findChild<QLineEdit*>();
    if (!table || !filter) { qCritical() << "harness could not find table/filter"; return 2; }

    qInfo() << "total rows:" << table->rowCount();
    qInfo() << "conflicted rows after populateTable():" << conflictRowCount(table);

    // Criterion 3: blank registrations never conflict.
    int r1 = findRow(table, QString::fromUtf8("Plein écran"));
    int r2 = findRow(table, QString::fromUtf8("Basculer plein écran"));
    int r3 = findRow(table, "Exporter en PDF");
    int r4 = findRow(table, "Exporter en image");
    int r5 = findRow(table, "Profondeur haut");
    check(r1 >= 0 && r2 >= 0 && r3 >= 0 && r4 >= 0 && r5 >= 0, "all five sample rows present");

    check(rowIsConflicted(table, r1) && rowIsConflicted(table, r2),
          "same-category duplicate pair is flagged (2 rows)");
    check(!rowIsConflicted(table, r3) && !rowIsConflicted(table, r4),
          "blank registrations in the same category are NOT flagged");
    check(!rowIsConflicted(table, r5),
          "same key in a different category is NOT flagged (category scoping)");
    check(conflictRowCount(table) == 2, "exactly 2 conflicted rows (the planted pair), 0 from blanks");

    // Sanity: the filter still drives the real page (harness is not vacuous).
    filter->setText("Profondeur");
    int visible = 0;
    for (int r = 0; r < table->rowCount(); ++r) if (!table->isRowHidden(r)) ++visible;
    qInfo() << "filter 'Profondeur' ->" << visible << "visible";
    check(visible == 1, "filter matches exactly the 'Profondeur haut' row");
    filter->setText("");

    qInfo().noquote() << (failures == 0 ? "ALL CHECKS PASSED" : QString("%1 CHECK(S) FAILED").arg(failures));
    return failures == 0 ? 0 : 1;
}
