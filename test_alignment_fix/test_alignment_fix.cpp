// Standalone test for issue #283: verify Qt::AlignHCenter round-trips correctly
// through QMetaEnum (the mechanism addtabledialog.cpp uses to save/load alignment).
#include <QMetaEnum>
#include <QDebug>
#include <cstdlib>

int main()
{
    auto me = QMetaEnum::fromType<Qt::Alignment>();

    // ── Part 1: confirm the enum values ──────────────────────────────────────
    const int alignHCenter = static_cast<int>(Qt::AlignHCenter); // 0x0004
    const int alignCenter  = static_cast<int>(Qt::AlignCenter);  // 0x0084
    qDebug() << "Qt::AlignHCenter =" << alignHCenter;
    qDebug() << "Qt::AlignCenter  =" << alignCenter;

    // ── Part 2: simulate saveConfig ──────────────────────────────────────────
    // headerAlignment() returns Qt::AlignHCenter; valueToKey() serialises it.
    const char* saved = me.valueToKey(alignHCenter);
    qDebug() << "Saved to JSON as:" << saved;  // expects "AlignHCenter"

    // ── Part 3: simulate loadConfig ──────────────────────────────────────────
    // keyToValue reads the string back to an int.
    const int loaded = me.keyToValue(saved);
    qDebug() << "Decoded from JSON:" << loaded;  // expects 4

    // ── Part 4: the switch that was broken ───────────────────────────────────
    // OLD code:  case Qt::AlignCenter  (132) — never matched 4 → default (Right)
    // NEW code:  case Qt::AlignHCenter (4)   — matches → Centre (index 1)
    int old_index = -1;
    switch (loaded) {
        case Qt::AlignLeft:
            old_index = 0; break;
        case Qt::AlignCenter:     // old buggy check
            old_index = 1; break;
        default:
            old_index = 2; break; // bug: lands here for AlignHCenter
    }

    int new_index = -1;
    switch (loaded) {
        case Qt::AlignLeft:
            new_index = 0; break;
        case Qt::AlignHCenter:    // fixed check
        case Qt::AlignCenter:     // backward-compat for hand-edited JSON
            new_index = 1; break;
        default:
            new_index = 2; break;
    }

    qDebug() << "";
    qDebug() << "OLD loadConfig combobox index:" << old_index
             << (old_index == 1 ? "(Center)" : (old_index == 0 ? "(Left)" : "(Right) ← BUG"));
    qDebug() << "NEW loadConfig combobox index:" << new_index
             << (new_index == 1 ? "(Center) ← CORRECT" : "STILL WRONG");

    const bool pass = (old_index == 2) && (new_index == 1);
    qDebug() << "";
    qDebug() << (pass ? "PASS: bug confirmed before fix, correct after fix."
                      : "FAIL: unexpected result — check Qt enum values.");
    return pass ? EXIT_SUCCESS : EXIT_FAILURE;
}
