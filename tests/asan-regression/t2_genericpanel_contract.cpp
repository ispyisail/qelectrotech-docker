// t2_genericpanel_contract.cpp
//
// Targeted ASan + behavioural regression test for PR #519 —
// GenericPanel::getItemForDiagram() leak fix.
//
//   sources/genericpanel.cpp
//       QTreeWidgetItem *getItemForDiagram(Diagram *diagram, bool *created) {
//           if (!diagram) return nullptr;
//           QTreeWidgetItem *it = diagrams_.value(diagram, nullptr);
//           if (it) { if (created) *created = false; return it; }
//   +       if (!created) return nullptr;          // <-- the patch
//           it = makeItem(QET::Diagram);
//   -       if (created) *created = true;
//   +       *created = true;
//           return it;
//       }
//
// Reviewer concern (PR review) + PLC-user (sources/genericpanel.cpp:328,
//   "Don't we change the logic with these modifications?"):
//   The patch changes the contract of the no-`created`-argument overload:
//   for an UNcached diagram it now returns nullptr instead of a freshly
//   allocated, parentless, UNREGISTERED QTreeWidgetItem that the caller
//   immediately leaks.
//
// This test replicates the exact function and ALL real caller patterns and
// asserts, under ASan:
//   (1) addDiagram() path (always passes &created): unchanged — item created,
//       created==true, item registered, no leak. [regression guard]
//   (2) cached-diagram lookup with no `created` arg: unchanged — returns the
//       cached item. [regression guard]
//   (3) UNcached diagram with no `created` arg, behind the real caller guard
//       `if (item) ...`:
//          LEGACY  -> returns orphan item, caller discards it -> ASan LEAK.
//          PATCHED -> returns nullptr, guard skips -> no leak, no crash.
//
// Real call sites that use the no-`created` overload (all guard with if(item)):
//   sources/qetdiagrameditor.cpp:1857,1870   (setCurrentItem)
//   sources/elementspanelwidget.cpp:273..375 (setSelected)

#include <QApplication>
#include <QTreeWidget>
#include <QHash>
#include <cassert>
#include <cstdio>

struct Diagram { int id; };         // stand-in for QET Diagram

class Panel : public QTreeWidget {  // mirrors GenericPanel
	QHash<Diagram*, QTreeWidgetItem*> diagrams_;
public:
	// mirrors makeItem(QET::Diagram): a parentless QTreeWidgetItem.
	QTreeWidgetItem *makeItem() { return new QTreeWidgetItem(); }

	// Verbatim transcription of the patched getItemForDiagram logic.
	QTreeWidgetItem *getItemForDiagram(Diagram *diagram, bool *created = nullptr)
	{
		if (!diagram) return nullptr;
		QTreeWidgetItem *it = diagrams_.value(diagram, nullptr);
		if (it) { if (created) *created = false; return it; }
#ifndef LEGACY
		if (!created) return nullptr;          // <-- the patch
		it = makeItem();
		*created = true;
#else
		it = makeItem();                       // pre-patch behaviour
		if (created) *created = true;
#endif
		return it;
	}

	// mirrors the freshly_created branch of updateDiagramItem(): register the
	// new item in the cache and adopt it into the tree (so the tree owns it).
	void registerItem(Diagram *d, QTreeWidgetItem *it) {
		diagrams_.insert(d, it);
		addTopLevelItem(it);                   // tree takes ownership
	}
};

int main(int argc, char **argv)
{
	QApplication app(argc, argv);   // QTreeWidget is a QWidget
	Panel panel;
	Diagram dA{1}, dB{2}, dC{3};

	// (1) addDiagram() path — always passes &created. Must be unchanged.
	{
		bool created = false;
		QTreeWidgetItem *it = panel.getItemForDiagram(&dA, &created);
		assert(it && "addDiagram path must return a valid item");
		assert(created && "uncached diagram must report created==true");
		panel.registerItem(&dA, it);           // tree owns it -> no leak
	}

	// (2) cached lookup with NO created arg — must still return the item.
	{
		QTreeWidgetItem *it = panel.getItemForDiagram(&dA);
		assert(it == panel.topLevelItem(0) &&
		       "cached lookup must return the registered item");
	}

	// (3) UNcached diagram, NO created arg, behind the real caller guard.
	//     LEGACY leaks an orphan here; PATCHED returns nullptr.
	{
		QTreeWidgetItem *item = panel.getItemForDiagram(&dB);   // uncached
		if (item) {                 // <-- the guard every real caller uses
			panel.setCurrentItem(item);
			// real callers do NOT register or free it -> LEGACY leaks here
		}
#ifndef LEGACY
		assert(item == nullptr &&
		       "patched: uncached + no-created overload returns nullptr");
#endif
	}

	// Sanity: a second uncached, unguarded scenario to exercise dC too.
	{
		QTreeWidgetItem *item = panel.getItemForDiagram(&dC);
		if (item) panel.setCurrentItem(item);
	}

	std::printf("t2: getItemForDiagram contract assertions passed\n");
	return 0;
}
