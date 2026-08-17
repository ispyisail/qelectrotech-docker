// S6 verification harness: drives the real ShortcutsConfigPage offscreen.
#include <QApplication>
#include <QAction>
#include <QBrush>
#include <QColor>
#include <QComboBox>
#include <QDebug>
#include <QKeySequenceEdit>
#include <QLabel>
#include <QLineEdit>
#include <QMap>
#include <QPushButton>
#include <QToolButton>
#include <QTreeWidget>
#include <QTreeWidgetItem>
#include "shortcutmanager.h"
#include "shortcutsconfigpage.h"

static int failures = 0;
static void check(bool ok, const QString &what) {
    qInfo().noquote() << (ok ? "    PASS  " : "    FAIL  ") << what;
    if (!ok) ++failures;
}

static int totalActionRows(QTreeWidget *t) {
    int n = 0;
    for (int i = 0; i < t->topLevelItemCount(); ++i) n += t->topLevelItem(i)->childCount();
    return n;
}

static int visibleActionRows(QTreeWidget *t) {
    int n = 0;
    for (int i = 0; i < t->topLevelItemCount(); ++i) {
        QTreeWidgetItem *top = t->topLevelItem(i);
        for (int j = 0; j < top->childCount(); ++j) {
            if (!top->child(j)->isHidden()) ++n;
        }
    }
    return n;
}

static int visibleCategoryNodes(QTreeWidget *t) {
    int n = 0;
    for (int i = 0; i < t->topLevelItemCount(); ++i) {
        if (!t->topLevelItem(i)->isHidden()) ++n;
    }
    return n;
}

static QMap<QString, int> categoryChildCounts(QTreeWidget *t) {
    QMap<QString, int> m;
    for (int i = 0; i < t->topLevelItemCount(); ++i) {
        m.insert(t->topLevelItem(i)->text(0), t->topLevelItem(i)->childCount());
    }
    return m;
}

static QTreeWidgetItem *findActionItem(QTreeWidget *t, const QString &description) {
    for (int i = 0; i < t->topLevelItemCount(); ++i) {
        QTreeWidgetItem *top = t->topLevelItem(i);
        for (int j = 0; j < top->childCount(); ++j) {
            QTreeWidgetItem *child = top->child(j);
            if (child->text(0) == description) return child;
        }
    }
    return nullptr;
}

int main(int argc, char **argv) {
    QApplication app(argc, argv);

    // Register a representative sample across 3 categories, including BLANK
    // registrations (the §2 design) and a deliberately planted conflict pair.
    QAction a1, a2, a3, a4, a5, a6, a7;
    auto &m = ShortcutManager::instance();
    a1.setText(QString::fromUtf8("Plein écran"));          m.registerAction(&a1, "mainwindow.fullscreen",       QString::fromUtf8("Général"),    QKeySequence("Ctrl+Shift+F"));
    a2.setText("Exporter en PDF");                         m.registerAction(&a2, "file.export_pdf",             "Fichier",                    QKeySequence());
    a3.setText("Profondeur haut");                         m.registerAction(&a3, "depth.raise",                 "Profondeur",                 QKeySequence("Ctrl+Shift+Up"));
    a4.setText("Enregistrer");                             m.registerAction(&a4, "file.save",                   "Fichier",                    QKeySequence("Ctrl+S"));
    a5.setText("Nouveau");                                 m.registerAction(&a5, "file.new",                    "Fichier",                    QKeySequence("Ctrl+N"));
    a6.setText(QString::fromUtf8("Basculer plein écran")); m.registerAction(&a6, "mainwindow.toggle_fullscreen", QString::fromUtf8("Général"), QKeySequence("Ctrl+Shift+F"));
    a7.setText("Exporter en image");                       m.registerAction(&a7, "file.export_image",           "Fichier",                    QKeySequence());

    ShortcutsConfigPage page;
    auto *tree   = page.findChild<QTreeWidget*>();
    auto *filter = page.findChild<QLineEdit*>();
    auto *combo  = page.findChild<QComboBox*>("quickFilterCombo");
    auto *count  = page.findChild<QLabel*>("shortcutCountLabel");
    if (!tree || !filter || !combo || !count) { qCritical() << "harness could not find tree/filter/combo/count"; return 2; }

    qInfo().noquote() << "== Criterion 1: search gaps close ==";
    qInfo() << "total rows:" << totalActionRows(tree) << " visible:" << visibleActionRows(tree);
    struct { const char *q; const char *why; } probes[] = {
        {"Ctrl+S",      "search by key sequence"},
        {"export pdf",  "multi-keyword, different word order"},
        {"general",     "accent-insensitive (matches 'Général')"},
        {"Profondeur",  "plain category match (control)"},
    };
    for (auto &p : probes) {
        filter->setText(p.q);
        qInfo().noquote() << QString("  query %1 -> %2 visible   [%3]")
            .arg(QString("'%1'").arg(p.q), -14).arg(visibleActionRows(tree), 3).arg(p.why);
    }
    filter->setText("");

    // Re-measure each gap against its required threshold.
    filter->setText("Ctrl+S");     check(visibleActionRows(tree) >= 1, "Ctrl+S search by key finds its binding");
    filter->setText("export pdf"); check(visibleActionRows(tree) >= 1, "export pdf multi-keyword matches 'Exporter en PDF'");
    filter->setText("general");    check(visibleActionRows(tree) >= 1, "general accent-insensitive matches 'Général'");
    filter->setText("Profondeur"); check(visibleActionRows(tree) >= 1, "Profondeur control still matches");
    filter->setText("");

    qInfo().noquote() << "== Criterion 2: tree groups by category ==";
    const QMap<QString, int> actual = categoryChildCounts(tree);
    qInfo().noquote() << "  top-level nodes:" << tree->topLevelItemCount();
    for (auto it = actual.cbegin(); it != actual.cend(); ++it)
        qInfo().noquote() << "    category" << it.key() << "->" << it.value() << "children";
    check(tree->topLevelItemCount() == 3, "one top-level node per distinct category (3 categories)");
    check(actual.value(QString::fromUtf8("Général"))    == 2, "Général holds 2 children");
    check(actual.value("Fichier")                        == 4, "Fichier holds 4 children");
    check(actual.value("Profondeur")                     == 1, "Profondeur holds 1 child");

    qInfo().noquote() << "== Criterion 3: quick filters partition the set ==";
    const int total = totalActionRows(tree);
    combo->setCurrentIndex(0); int all = visibleActionRows(tree);
    combo->setCurrentIndex(1); int bound = visibleActionRows(tree);
    combo->setCurrentIndex(2); int unbound = visibleActionRows(tree);
    combo->setCurrentIndex(3); int conflicts = visibleActionRows(tree);
    qInfo().noquote() << QString("  All=%1  Bound=%2  Unbound=%3  Conflicts=%4  (total %5)")
        .arg(all).arg(bound).arg(unbound).arg(conflicts).arg(total);
    check(all == total, "All filter shows every action");
    check(bound + unbound == total, "Bound + Unbound partition the whole set");
    check(conflicts == 2, "Conflicts filter shows the planted duplicate pair (2)");

    // Remove the planted conflict: give a6 a unique sequence and re-run detection.
    QTreeWidgetItem *a6item = findActionItem(tree, QString::fromUtf8("Basculer plein écran"));
    auto *a6edit = qobject_cast<QKeySequenceEdit*>(tree->itemWidget(a6item, 1));
    check(a6item && a6edit, "found the planted-conflict row's edit");
    a6edit->setKeySequence(QKeySequence("Ctrl+Alt+F"));
    a6edit->editingFinished(); // re-run checkConflicts exactly as a user edit would
    combo->setCurrentIndex(3); int conflicts_after = visibleActionRows(tree);
    qInfo() << "  after removing duplicate -> Conflicts:" << conflicts_after;
    check(conflicts_after == 0, "Conflicts filter shows nothing once the duplicate is removed");

    qInfo().noquote() << "== Criterion 4: reset / highlight / persistence ==";
    // Conflict highlighting is live in the freshly-populated tree (before we removed it):
    // rebuild a clean page to observe the highlight deterministically.
    // (Simpler: re-plant by setting a6 back to the conflicting sequence and re-running.)
    a6edit->setKeySequence(QKeySequence("Ctrl+Shift+F"));
    a6edit->editingFinished();
    QTreeWidgetItem *a1item = findActionItem(tree, QString::fromUtf8("Plein écran"));
    auto *a1edit = qobject_cast<QKeySequenceEdit*>(tree->itemWidget(a1item, 1));
    const QColor conflict_color(255, 205, 205);
    check(a1item && a1item->background(0).color() == conflict_color, "conflict row 1 highlighted red");
    check(a6item && a6item->background(0).color() == conflict_color, "conflict row 2 highlighted red");
    check(!a1edit->toolTip().isEmpty() && !a6edit->toolTip().isEmpty(), "conflict tooltips explain the collision");
    check(findActionItem(tree, "Enregistrer")->background(0).color() != conflict_color, "non-conflicting row not highlighted");

    // Per-row reset.
    QTreeWidgetItem *a4item = findActionItem(tree, "Enregistrer");
    auto *a4edit = qobject_cast<QKeySequenceEdit*>(tree->itemWidget(a4item, 1));
    auto *a4reset = qobject_cast<QToolButton*>(tree->itemWidget(a4item, 2));
    a4edit->setKeySequence(QKeySequence("Ctrl+Shift+S"));
    a4reset->click();
    check(a4edit->keySequence() == QKeySequence("Ctrl+S"), "per-row reset restores the default sequence");

    // "Tout réinitialiser".
    auto *reset_all = page.findChild<QPushButton*>();
    a4edit->setKeySequence(QKeySequence("Ctrl+Shift+S"));
    QTreeWidgetItem *a5item = findActionItem(tree, "Nouveau");
    auto *a5edit = qobject_cast<QKeySequenceEdit*>(tree->itemWidget(a5item, 1));
    a5edit->setKeySequence(QKeySequence("Ctrl+Shift+N"));
    reset_all->click();
    check(a4edit->keySequence() == QKeySequence("Ctrl+S") && a5edit->keySequence() == QKeySequence("Ctrl+N"),
          "Tout réinitialiser restores every row");

    // Persistence through applyConf().
    a4edit->setKeySequence(QKeySequence("Ctrl+Shift+Z"));
    page.applyConf();
    check(ShortcutManager::instance().currentSequence("file.save") == QKeySequence("Ctrl+Shift+Z"),
          "applyConf persists the edited sequence through ShortcutManager");

    // Count label tracks the filtered set.
    combo->setCurrentIndex(0);
    filter->setText("general");
    const int general = visibleActionRows(tree);
    qInfo().noquote() << "  count label after 'general':" << count->text() << "(visible" << general << ")";
    check(count->text().contains(QString::number(general)), "N actions label matches the visible count");
    filter->setText("");

    qInfo().noquote() << (failures == 0 ? "ALL CHECKS PASSED" : QString("%1 CHECK(S) FAILED").arg(failures));
    return failures == 0 ? 0 : 1;
}
