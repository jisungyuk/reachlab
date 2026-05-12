TASK_KEY   = 'reaching'
TASK_LABEL = 'Reaching Task'

TARGETS_SCREEN  = 'reaching_targets'
SESSIONS_SCREEN = 'reaching_sessions'
GAME_SCREEN     = 'reaching_game'


def build_screens(main_window, state):
    from tasks.reaching.targets  import TargetScreen
    from tasks.reaching.sessions import SessionScreen
    from tasks.reaching.game     import GameScreen
    return {
        TARGETS_SCREEN:  TargetScreen(state, main_window),
        SESSIONS_SCREEN: SessionScreen(state, main_window),
        GAME_SCREEN:     GameScreen(state, main_window.liberty, main_window),
    }
