// S6 verification harness: drives the real ShortcutsConfigPage offscreen.
#include <QApplication>
#include <QAction>
#include <QLineEdit>
#include <QTableWidget>
#include <QDebug>
#include "shortcutmanager.h"
#include "shortcutsconfigpage.h"

static int visibleRows(QTableWidget *t) {
    int n = 0;
    for (int r = 0; r < t->rowCount(); ++r) if (!t->isRowHidden(r)) ++n;
    return n;
}

int main(int argc, char **argv) {
    QApplication app(argc, argv);

    // Register a representative sample, including BLANK ones (the §2 design).
    QAction a1, a2, a3, a4;
    auto &m = ShortcutManager::instance();
    a1.setText(QString::fromUtf8("Plein écran"));     m.registerAction(&a1, "mainwindow.fullscreen", QString::fromUtf8("Général"), QKeySequence("Ctrl+Shift+F"));
    a2.setText("Exporter en PDF"); m.registerAction(&a2, "file.export_pdf",       "Fichier", QKeySequence());
    a3.setText("Profondeur haut"); m.registerAction(&a3, "depth.raise",           "Profondeur", QKeySequence("Ctrl+Shift+Up"));
    a4.setText("Enregistrer");     m.registerAction(&a4, "file.save",             "Fichier", QKeySequence("Ctrl+S"));

    ShortcutsConfigPage page;
    auto *table  = page.findChild<QTableWidget*>();
    auto *filter = page.findChild<QLineEdit*>();
    if (!table || !filter) { qCritical() << "harness could not find table/filter"; return 2; }

    qInfo() << "total rows:" << table->rowCount() << " visible:" << visibleRows(table);

    struct { const char *q; const char *why; } probes[] = {
        {"Ctrl+S",      "search by key sequence"},
        {"export pdf",  "multi-keyword, different word order"},
        {"general",     "accent-insensitive (matches 'General'/'General')"},
        {"Profondeur",  "plain category match (should work today)"},
    };
    for (auto &p : probes) {
        filter->setText(p.q);
        qInfo().noquote() << QString("  query %1 -> %2 visible   [%3]")
            .arg(QString("'%1'").arg(p.q), -14).arg(visibleRows(table), 3).arg(p.why);
    }
    filter->setText("");
    qInfo() << "cleared ->" << visibleRows(table) << "visible";
    return 0;
}
