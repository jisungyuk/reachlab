TASK_KEY     = 'reaching'
TASK_LABEL   = 'Reaching Task'
HAS_TARGETS  = True
HAS_SESSIONS = True

TARGETS_SCREEN  = 'reaching_targets'
SESSIONS_SCREEN = 'reaching_sessions'
GAME_SCREEN     = 'reaching_game'


def check_start(main_window, state):
    """Called by the menu before the game starts. Blocks the start when the
    session has trials (from state.start_trial on) for a hand that the
    digitization hand setup does not record. Returns (title, message) to
    block, or None."""
    from tasks.reaching.recorder import recorded_hands
    scr = main_window.screens.get(SESSIONS_SCREEN)
    if scr is None:
        return None
    allowed = recorded_hands(state)
    bad = {'right': [], 'left': []}
    for r in range(max(0, state.start_trial - 1), scr.table.rowCount()):
        item = scr.table.item(r, 1)
        hand = 'left' if item and item.text().strip() == '2' else 'right'
        if hand not in allowed:
            bad[hand].append(str(r + 1))
    lines = [f"{hand.capitalize()}-hand trials: {', '.join(rows)}"
             for hand, rows in bad.items() if rows]
    if not lines:
        return None
    setup = allowed[0].capitalize()
    return ("Hand Mismatch",
            f"Digitization is set to {setup} (Mode {state.dig_mode}) but the session "
            f"contains trials for the other hand, which would not be recorded.\n\n"
            + '\n'.join(lines) +
            "\n\nChange the digitization hand setup or the session file before starting.")


def build_screens(main_window, state):
    from tasks.reaching.targets  import TargetScreen
    from tasks.reaching.sessions import SessionScreen
    from tasks.reaching.game     import GameScreen
    return {
        TARGETS_SCREEN:  TargetScreen(state, main_window),
        SESSIONS_SCREEN: SessionScreen(state, main_window),
        GAME_SCREEN:     GameScreen(state, main_window.liberty, main_window),
    }
