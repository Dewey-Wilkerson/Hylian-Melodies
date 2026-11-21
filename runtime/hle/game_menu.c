// The port's settings as rows of the game's own Options menu (branch in-game-gui; docs/IN-GAME-MENU.md).
//
// Function hooks (recomp/hooks.txt) on the supported game version:
//  - the Options screen builder: after it ran, Yes/No rows of the game's own toggle class are added to the Graphics
//    page (found by its first row's label), their values and change callbacks ours;
//  - the toggle's per-frame update: keeps our Fullscreen row in step when F11 / Alt+Enter switch;
//  - the text lookup (text id -> style and UTF-32 text): ids from HM_TEXT_BASE up are ours (labels and descriptions,
//    in the game's languages), every other id goes to the game.
// Everything below is how this game version lays out its objects, found by reading the lifted code (facts only:
// addresses, offsets, sizes). Guest memory is host memory, so the game's objects are read and written in place.
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "../hle.h"
#include "../romfs_build.h"
#include "../settings.h"

// game functions and data (1.4.0)
#define G_NEW            0x70007c80a0ull  // operator new(size) -> x0
#define G_DELETE         0x70007c80b0ull  // operator delete(p)
#define G_TOGGLE_CTOR    0x70000662b0ull  // (row, label id, desc id, const std::string *key, std::function<void(bool)> *, default, 0, 0)
#define G_VEC_PUSH_SLOW  0x7000012b90ull  // vector<unique_ptr<Row>>::push_back slow path (vec, unique_ptr *)
#define G_BIND_VT_GOT    0x7000a34fa0ull  // GOT slot: vtable of the bound member function the toggles take
#define ROW_SIZE         0x90
#define ROW_LABEL        0x08             // u32 text id
#define ROW_VALUE        0x88             // u8 current value of a toggle
#define ROW_VT_REFRESH   0x30             // vtable slots the toggle constructor calls after setting the value:
#define ROW_VT_REFRESH2  0x28             //   refresh(row), then (row, 0)
#define SCREEN_PAGES     0x68             // vector<vector<unique_ptr<Row>>> in the Options screen object
#define LABEL_DISCO      70               // first row of the Graphics page

// ---- our text (the lookup hook borrows a game text of the same kind for the style field: text_style below)
enum {
    HM_TEXT_BASE = 0x484d0000,
    T_FULLSCREEN = HM_TEXT_BASE, T_FULLSCREEN_DESC, T_PACING, T_PACING_DESC, T_FILTER, T_FILTER_DESC,
    T_SHARP, T_SMOOTH, T_NEAREST, T_PIXEL,
    T_PAUSE_TITLE, T_PAUSE_TITLE_DESC, T_PAUSE_QUIT_DESC, T_CONFIRM_TITLE, T_CONFIRM_QUIT,
    T_CONTROLS, T_CONTROLS_DESC, T_RESET, T_RESET_DESC, T_BIND_DESC, T_CAPTURE,
    T_BIND_LABEL,                  // 16: the Switch buttons, in runtime/ui/input.c's order
    T_COUNT = T_BIND_LABEL + 16,   // (the fixed texts end here)
    T_BIND_VALUE = T_COUNT,        // 16 made at lookup time: each button's bindings
    T_END = T_BIND_VALUE + 16
};
#define TEXT_LABEL  LABEL_DISCO        // a row label of the game's
#define TEXT_DESC   (LABEL_DISCO + 1)  // a row description
#define TEXT_CHOICE 0x88               // a choice name (the Language row's first)
#define TEXT_BUTTON 48                 // a main-list button and its description
#define TEXT_BUTTON_DESC 49
static const uint32_t text_style[T_COUNT - HM_TEXT_BASE] = {
    TEXT_LABEL, TEXT_DESC, TEXT_LABEL, TEXT_DESC, TEXT_LABEL, TEXT_DESC, TEXT_CHOICE, TEXT_CHOICE, TEXT_CHOICE,
    TEXT_CHOICE, TEXT_LABEL, TEXT_DESC, TEXT_DESC, TEXT_DESC, TEXT_DESC,
    TEXT_BUTTON, TEXT_BUTTON_DESC, TEXT_BUTTON, TEXT_BUTTON_DESC, TEXT_DESC, TEXT_CHOICE,
    TEXT_LABEL, TEXT_LABEL, TEXT_LABEL, TEXT_LABEL, TEXT_LABEL, TEXT_LABEL, TEXT_LABEL, TEXT_LABEL,
    TEXT_LABEL, TEXT_LABEL, TEXT_LABEL, TEXT_LABEL, TEXT_LABEL, TEXT_LABEL, TEXT_LABEL, TEXT_LABEL,
};

// The game's language codes (localization.xml), in this order in every row below. Translations other than English
// were drafted by the agent; a native check is wanted.
static const char *const langs[] = {"en", "ja", "de", "fr", "cafr", "es", "uses", "it", "kr", "sc", "tc"};
enum { NLANG = sizeof langs / sizeof *langs };

#define SAME(t) {t, t, t, t, t, t, t, t, t, t, t}
static const char *const texts[T_COUNT - HM_TEXT_BASE][NLANG] = {
    {"FULLSCREEN", "フルスクリーン", "VOLLBILD", "PLEIN ÉCRAN", "PLEIN ÉCRAN", "PANTALLA COMPLETA", "PANTALLA COMPLETA",
     "SCHERMO INTERO", "전체 화면", "全屏", "全螢幕"},
    {"Fill the screen (borderless, at the desktop's resolution). F11 or Alt+Enter also switch.",
     "画面全体に表示します（枠なし、デスクトップの解像度）。F11 または Alt+Enter でも切り替えられます。",
     "Füllt den Bildschirm (randlos, in der Auflösung des Desktops). F11 oder Alt+Eingabe schalten ebenfalls um.",
     "Occupe tout l'écran (sans bordure, à la résolution du bureau). F11 ou Alt+Entrée basculent aussi.",
     "Occupe tout l'écran (sans bordure, à la résolution du bureau). F11 ou Alt+Entrée basculent aussi.",
     "Ocupa toda la pantalla (sin bordes, a la resolución del escritorio). F11 o Alt+Intro también cambian el modo.",
     "Ocupa toda la pantalla (sin bordes, con la resolución del escritorio). F11 o Alt+Enter también cambian el modo.",
     "Riempie lo schermo (senza bordi, alla risoluzione del desktop). Anche F11 o Alt+Invio cambiano modalità.",
     "화면 전체에 표시합니다(테두리 없음, 바탕 화면 해상도). F11 또는 Alt+Enter로도 전환할 수 있습니다.",
     "填满整个屏幕（无边框，使用桌面分辨率）。也可按 F11 或 Alt+Enter 切换。",
     "填滿整個螢幕（無邊框，使用桌面解析度）。也可按 F11 或 Alt+Enter 切換。"},
    {"FRAME PACING", "フレームペーシング", "BILDTAKT", "CADENCE D'IMAGES", "CADENCE D'IMAGES", "RITMO DE FOTOGRAMAS",
     "RITMO DE CUADROS", "CADENZA FOTOGRAMMI", "프레임 페이싱", "帧同步", "影格同步"},
    {"A steady 60 Hz, like the Switch's display. Turn it off only if the picture stutters evenly.",
     "Switch の画面と同じ安定した 60 Hz で表示します。映像が規則的にカクつく場合のみオフにしてください。",
     "Gleichmäßige 60 Hz wie auf dem Bildschirm der Switch. Nur ausschalten, wenn das Bild gleichmäßig ruckelt.",
     "Un 60 Hz régulier, comme l'écran de la Switch. Désactivez-le seulement si l'image saccade de façon régulière.",
     "Un 60 Hz régulier, comme l'écran de la Switch. Désactivez-le seulement si l'image saccade de façon régulière.",
     "60 Hz constantes, como la pantalla de Switch. Desactívalo solo si la imagen da tirones regulares.",
     "60 Hz constantes, como la pantalla de Switch. Desactívalo solo si la imagen se traba de forma regular.",
     "60 Hz costanti, come lo schermo di Switch. Disattivalo solo se l'immagine scatta in modo regolare.",
     "Switch 화면처럼 안정적인 60Hz로 표시합니다. 화면이 일정하게 끊길 때만 끄세요.",
     "像 Switch 屏幕一样稳定的 60 Hz。仅在画面规律性卡顿时关闭。",
     "像 Switch 螢幕一樣穩定的 60 Hz。僅在畫面規律性卡頓時關閉。"},
    {"SCALING FILTER", "スケーリングフィルター", "SKALIERUNGSFILTER", "MISE À L'ÉCHELLE", "MISE À L'ÉCHELLE",
     "FILTRO DE ESCALADO", "FILTRO DE ESCALADO", "FILTRO DI SCALATURA", "스케일링 필터", "缩放滤镜", "縮放濾鏡"},
    {"How the picture is scaled to fit the window: Sharp (crisp pixels), Smooth, Nearest, or Pixel-perfect (whole-number steps only, with black borders). Takes effect at the next start.",
     "画面をウィンドウに合わせて拡大する方法：シャープ（くっきりしたドット）、スムーズ、ニアレスト、整数倍（整数倍のみ、周囲は黒帯）。次回の起動時に反映されます。",
     "Wie das Bild an das Fenster angepasst wird: Scharf (klare Pixel), Weich, Blockig oder Pixelgenau (nur ganzzahlige Stufen, mit schwarzem Rand). Wirkt ab dem nächsten Start.",
     "Comment l'image est adaptée à la fenêtre : Net (pixels francs), Lisse, Pixelisé ou Pixel parfait (multiples entiers seulement, bandes noires). Prend effet au prochain démarrage.",
     "Comment l'image est adaptée à la fenêtre : Net (pixels francs), Lisse, Pixelisé ou Pixel parfait (multiples entiers seulement, bandes noires). Prend effet au prochain démarrage.",
     "Cómo se ajusta la imagen a la ventana: Nítido (píxeles definidos), Suave, Pixelado o Píxel perfecto (solo múltiplos enteros, con bordes negros). Se aplica en el próximo inicio.",
     "Cómo se ajusta la imagen a la ventana: Nítido (píxeles definidos), Suave, Pixelado o Píxel perfecto (solo múltiplos enteros, con bordes negros). Se aplica la próxima vez que inicies.",
     "Come l'immagine viene adattata alla finestra: Nitido (pixel definiti), Morbido, Pixelato o Pixel perfetto (solo multipli interi, con bordi neri). Ha effetto dal prossimo avvio.",
     "화면을 창에 맞게 늘리는 방식: 선명하게(또렷한 픽셀), 부드럽게, 최근접, 정수배(정수 배율만, 검은 테두리). 다음 실행부터 적용됩니다.",
     "画面缩放到窗口的方式：清晰（像素分明）、平滑、最近邻或整数倍（仅整数倍放大，四周黑边）。下次启动时生效。",
     "畫面縮放到視窗的方式：清晰（像素分明）、平滑、最近鄰或整數倍（僅整數倍放大，四周黑邊）。下次啟動時生效。"},
    {"Sharp", "シャープ", "Scharf", "Net", "Net", "Nítido", "Nítido", "Nitido", "선명하게", "清晰", "清晰"},
    {"Smooth", "スムーズ", "Weich", "Lisse", "Lisse", "Suave", "Suave", "Morbido", "부드럽게", "平滑", "平滑"},
    {"Nearest", "ニアレスト", "Blockig", "Pixelisé", "Pixelisé", "Pixelado", "Pixelado", "Pixelato", "최근접", "最近邻", "最近鄰"},
    {"Pixel-perfect", "整数倍", "Pixelgenau", "Pixel parfait", "Pixel parfait", "Píxel perfecto", "Píxel perfecto",
     "Pixel perfetto", "정수배", "整数倍", "整數倍"},
    {"SAVE AND RETURN TO TITLE", "保存してタイトルへ", "SPEICHERN UND ZUM TITEL", "SAUVEGARDER ET RETOUR AU TITRE",
     "SAUVEGARDER ET RETOUR AU TITRE", "GUARDAR Y VOLVER AL TÍTULO", "GUARDAR Y VOLVER AL TÍTULO", "SALVA E TORNA AL TITOLO",
     "저장하고 타이틀로", "保存并返回标题", "儲存並返回標題"},
    {"Save and go back to the title screen", "保存してタイトル画面に戻ります。",
     "Speichert deinen Fortschritt und bringt dich zum Titelbildschirm zurück.",
     "Sauvegarder et retourner à l'écran titre.", "Sauvegarder et retourner à l'écran titre.",
     "Guarda la partida y regresa a la pantalla de título.", "Guarda la partida y regresa a la pantalla de título.",
     "Salva e torna alla schermata del titolo.", "저장하고 타이틀 화면으로 돌아갑니다.", "保存并返回标题画面。",
     "儲存並返回標題畫面。"},
    {"Save and close the game", "保存してゲームを終了します。", "Speichert deinen Fortschritt und beendet das Spiel.",
     "Sauvegarder et fermer le jeu.", "Sauvegarder et fermer le jeu.", "Guarda la partida y cierra el juego.",
     "Guarda la partida y cierra el juego.", "Salva e chiudi il gioco.", "저장하고 게임을 종료합니다.", "保存并关闭游戏。",
     "儲存並關閉遊戲。"},
    {"Are you sure? Press A again to save and return to the title screen.",
     "よろしいですか？もう一度Aを押すと保存してタイトル画面に戻ります。",
     "Bist du sicher? Drücke erneut A, um zu speichern und zum Titelbildschirm zurückzukehren.",
     "Es-tu sûr ? Appuie de nouveau sur A pour sauvegarder et retourner à l'écran titre.",
     "Es-tu sûr ? Appuie de nouveau sur A pour sauvegarder et retourner à l'écran titre.",
     "¿Seguro? Pulsa A otra vez para guardar y volver a la pantalla de título.",
     "¿Seguro? Presiona A otra vez para guardar y volver a la pantalla de título.",
     "Sei sicuro? Premi di nuovo A per salvare e tornare alla schermata del titolo.",
     "정말입니까? A를 한 번 더 누르면 저장하고 타이틀 화면으로 돌아갑니다.",
     "确定吗？再按一次A保存并返回标题画面。", "確定嗎？再按一次A儲存並返回標題畫面。"},
    {"Are you sure? Press A again to save and close the game.",
     "よろしいですか？もう一度Aを押すと保存してゲームを終了します。",
     "Bist du sicher? Drücke erneut A, um zu speichern und das Spiel zu beenden.",
     "Es-tu sûr ? Appuie de nouveau sur A pour sauvegarder et fermer le jeu.",
     "Es-tu sûr ? Appuie de nouveau sur A pour sauvegarder et fermer le jeu.",
     "¿Seguro? Pulsa A otra vez para guardar y cerrar el juego.",
     "¿Seguro? Presiona A otra vez para guardar y cerrar el juego.",
     "Sei sicuro? Premi di nuovo A per salvare e chiudere il gioco.",
     "정말입니까? A를 한 번 더 누르면 저장하고 게임을 종료합니다.",
     "确定吗？再按一次A保存并关闭游戏。", "確定嗎？再按一次A儲存並關閉遊戲。"},
    {"CONTROLS", "操作設定", "STEUERUNG", "COMMANDES", "COMMANDES", "CONTROLES", "CONTROLES", "COMANDI", "조작 설정",
     "操作设置", "操作設定"},
    {"Change which keys and gamepad buttons do what", "キーボードとゲームパッドのボタン割り当てを変更します",
     "Tasten der Tastatur und des Gamepads neu belegen", "Changer les touches du clavier et les boutons de la manette",
     "Changer les touches du clavier et les boutons de la manette", "Cambia las teclas y los botones del mando",
     "Cambia las teclas y los botones del control", "Cambia i tasti della tastiera e del controller",
     "키보드와 게임패드 버튼 배치를 변경합니다", "更改键盘按键和手柄按钮的分配", "變更鍵盤按鍵和手把按鈕的配置"},
    {"RESET TO DEFAULTS", "初期設定に戻す", "STANDARD WIEDERHERSTELLEN", "RÉTABLIR PAR DÉFAUT", "RÉTABLIR PAR DÉFAUT",
     "RESTABLECER", "RESTABLECER", "RIPRISTINA PREDEFINITI", "기본값으로 되돌리기", "恢复默认设置", "恢復預設設定"},
    {"Put every key and gamepad button back to how they were at first", "すべてのキーとボタンを初期の割り当てに戻します",
     "Alle Tasten und Gamepad-Tasten auf die Standardbelegung zurücksetzen",
     "Remet toutes les touches et tous les boutons à leur réglage d'origine",
     "Remet toutes les touches et tous les boutons à leur réglage d'origine",
     "Devuelve todas las teclas y botones a su configuración original",
     "Devuelve todas las teclas y botones a su configuración original",
     "Riporta tutti i tasti e i pulsanti alle impostazioni originali", "모든 키와 버튼을 기본 배치로 되돌립니다",
     "将所有按键和按钮恢复为默认分配", "將所有按鍵和按鈕恢復為預設配置"},
    {"Press A, then the key or gamepad button to use. Esc or Home cancels.",
     "A を押してから、使うキーまたはゲームパッドのボタンを押してください。Esc か Home でキャンセル。",
     "A drücken, dann die gewünschte Taste oder Gamepad-Taste. Esc oder Home bricht ab.",
     "Appuyez sur A, puis sur la touche ou le bouton de manette voulu. Échap ou Home pour annuler.",
     "Appuyez sur A, puis sur la touche ou le bouton de manette voulu. Échap ou Home pour annuler.",
     "Pulsa A y luego la tecla o el botón del mando que quieras usar. Esc o Home cancela.",
     "Presiona A y luego la tecla o el botón del control que quieras usar. Esc o Home cancela.",
     "Premi A, poi il tasto o il pulsante del controller da usare. Esc o Home annulla.",
     "A를 누른 다음 사용할 키나 게임패드 버튼을 누르세요. Esc나 Home으로 취소합니다.",
     "按 A，然后按要使用的键盘按键或手柄按钮。按 Esc 或 Home 取消。",
     "按 A，然後按要使用的鍵盤按鍵或手把按鈕。按 Esc 或 Home 取消。"},
    {"Press a key or button...", "キーかボタンを押してください...", "Taste drücken...", "Appuyez sur une touche...",
     "Appuyez sur une touche...", "Pulsa una tecla o botón...", "Presiona una tecla o botón...",
     "Premi un tasto o pulsante...", "키나 버튼을 누르세요...", "请按键...", "請按鍵..."},
    // the Switch buttons (runtime/ui/input.c: a b x y lstick rstick l r zl zr plus minus left up right down)
    SAME("A"), SAME("B"), SAME("X"), SAME("Y"),
    {"LEFT STICK (PRESS)", "Lスティック押し込み", "LINKER STICK (DRÜCKEN)", "STICK GAUCHE (APPUI)", "STICK GAUCHE (APPUI)",
     "STICK IZQUIERDO (PULSAR)", "STICK IZQUIERDO (PRESIONAR)", "LEVETTA SINISTRA (PREMI)", "L 스틱 누르기", "按下左摇杆",
     "按下左搖桿"},
    {"RIGHT STICK (PRESS)", "Rスティック押し込み", "RECHTER STICK (DRÜCKEN)", "STICK DROIT (APPUI)", "STICK DROIT (APPUI)",
     "STICK DERECHO (PULSAR)", "STICK DERECHO (PRESIONAR)", "LEVETTA DESTRA (PREMI)", "R 스틱 누르기", "按下右摇杆",
     "按下右搖桿"},
    SAME("L"), SAME("R"), SAME("ZL"), SAME("ZR"), SAME("+"), SAME("-"),
    {"D-PAD LEFT", "十字ボタン左", "STEUERKREUZ LINKS", "CROIX GAUCHE", "CROIX GAUCHE", "CRUCETA IZQUIERDA",
     "CRUCETA IZQUIERDA", "CROCE SINISTRA", "방향 버튼 왼쪽", "十字键左", "十字鍵左"},
    {"D-PAD UP", "十字ボタン上", "STEUERKREUZ OBEN", "CROIX HAUT", "CROIX HAUT", "CRUCETA ARRIBA", "CRUCETA ARRIBA",
     "CROCE SU", "방향 버튼 위", "十字键上", "十字鍵上"},
    {"D-PAD RIGHT", "十字ボタン右", "STEUERKREUZ RECHTS", "CROIX DROITE", "CROIX DROITE", "CRUCETA DERECHA",
     "CRUCETA DERECHA", "CROCE DESTRA", "방향 버튼 오른쪽", "十字键右", "十字鍵右"},
    {"D-PAD DOWN", "十字ボタン下", "STEUERKREUZ UNTEN", "CROIX BAS", "CROIX BAS", "CRUCETA ABAJO", "CRUCETA ABAJO",
     "CROCE GIÙ", "방향 버튼 아래", "十字键下", "十字鍵下"},
};

// Gamepad buttons as the Controls page names them (by position, not the maker's letters), by SDL3 gamepad code
// (SDL_GAMEPAD_BUTTON_SOUTH = 0 .. DPAD_RIGHT = 14), then the left and right triggers (100 + 4, 100 + 5).
enum { NPADNAME = 17 };
static const char *const pad_names[NPADNAME][NLANG] = {
    {"Bottom face", "フェイス下", "Taste unten", "Bouton bas", "Bouton bas", "Botón abajo", "Botón abajo", "Tasto giù",
     "아래 버튼", "下方按键", "下方按鍵"},
    {"Right face", "フェイス右", "Taste rechts", "Bouton droit", "Bouton droit", "Botón derecha", "Botón derecha",
     "Tasto destro", "오른쪽 버튼", "右方按键", "右方按鍵"},
    {"Left face", "フェイス左", "Taste links", "Bouton gauche", "Bouton gauche", "Botón izquierda", "Botón izquierda",
     "Tasto sinistro", "왼쪽 버튼", "左方按键", "左方按鍵"},
    {"Top face", "フェイス上", "Taste oben", "Bouton haut", "Bouton haut", "Botón arriba", "Botón arriba", "Tasto su",
     "위 버튼", "上方按键", "上方按鍵"},
    {"Back", "バック", "Zurück", "Retour", "Retour", "Atrás", "Atrás", "Indietro", "뒤로", "返回", "返回"},
    SAME("Home"),
    {"Start", "スタート", "Start", "Start", "Start", "Start", "Start", "Start", "시작", "开始", "開始"},
    {"Left stick", "左スティック", "Linker Stick", "Stick gauche", "Stick gauche", "Stick izquierdo", "Stick izquierdo",
     "Levetta sinistra", "왼쪽 스틱", "左摇杆", "左搖桿"},
    {"Right stick", "右スティック", "Rechter Stick", "Stick droit", "Stick droit", "Stick derecho", "Stick derecho",
     "Levetta destra", "오른쪽 스틱", "右摇杆", "右搖桿"},
    {"Left shoulder", "左ショルダー", "Linke Schultertaste", "Bouton épaule G", "Bouton épaule G", "Botón superior izq.",
     "Botón superior izq.", "Dorsale sinistro", "왼쪽 숄더", "左肩键", "左肩鍵"},
    {"Right shoulder", "右ショルダー", "Rechte Schultertaste", "Bouton épaule D", "Bouton épaule D",
     "Botón superior der.", "Botón superior der.", "Dorsale destro", "오른쪽 숄더", "右肩键", "右肩鍵"},
    {"D-pad up", "十字キー上", "Steuerkreuz oben", "Croix haut", "Croix haut", "Cruceta arriba", "Cruceta arriba",
     "Croce su", "방향키 위", "十字键上", "十字鍵上"},
    {"D-pad down", "十字キー下", "Steuerkreuz unten", "Croix bas", "Croix bas", "Cruceta abajo", "Cruceta abajo",
     "Croce giù", "방향키 아래", "十字键下", "十字鍵下"},
    {"D-pad left", "十字キー左", "Steuerkreuz links", "Croix gauche", "Croix gauche", "Cruceta izquierda",
     "Cruceta izquierda", "Croce sinistra", "방향키 왼쪽", "十字键左", "十字鍵左"},
    {"D-pad right", "十字キー右", "Steuerkreuz rechts", "Croix droite", "Croix droite", "Cruceta derecha",
     "Cruceta derecha", "Croce destra", "방향키 오른쪽", "十字键右", "十字鍵右"},
    {"Left trigger", "左トリガー", "Linker Trigger", "Gâchette G", "Gâchette G", "Gatillo izq.", "Gatillo izq.",
     "Grilletto sinistro", "왼쪽 트리거", "左扳机", "左扳機"},
    {"Right trigger", "右トリガー", "Rechter Trigger", "Gâchette D", "Gâchette D", "Gatillo der.", "Gatillo der.",
     "Grilletto destro", "오른쪽 트리거", "右扳机", "右扳機"},
};

// runtime/ui/input.c (the game target; the headless one has none of it: the Controls page is then left out)
extern void input_capture_begin(int b) __attribute__((weak));
extern int input_capture_state(void) __attribute__((weak));
extern unsigned input_bindings_generation(void) __attribute__((weak));
extern int input_binding_codes(int b, bool padside, int *out, int max) __attribute__((weak));
extern const char *input_key_name(int scancode) __attribute__((weak));
extern void input_bindings_reset(void) __attribute__((weak));
static bool have_input(void) { return input_capture_begin && input_binding_codes; }

static const char *pad_name(int code, int l, char *tmp, size_t cap) {
    int i = code >= 0 && code <= 14 ? code : code == 104 ? 15 : code == 105 ? 16 : -1;
    if (i >= 0) return pad_names[i][l];
    snprintf(tmp, cap, "#%d", code);
    return tmp;
}

// "J, Return / Bottom face": button b's keys, then its gamepad buttons ("-" for a side with none)
static void binding_text(int b, int l, char *out, size_t cap) {
    int codes[4], n;
    size_t k = 0;
    out[0] = 0;
    for (int side = 0; side < 2; side++) {
        if (side) k += (size_t)snprintf(out + k, k < cap ? cap - k : 0, " / ");
        n = input_binding_codes(b, side, codes, 4);
        if (!n) k += (size_t)snprintf(out + k, k < cap ? cap - k : 0, "-");
        for (int i = 0; i < n; i++) {
            char tmp[16];
            const char *name = side ? pad_name(codes[i], l, tmp, sizeof tmp) : input_key_name(codes[i]);
            k += (size_t)snprintf(out + k, k < cap ? cap - k : 0, "%s%s", i ? ", " : "", name);
        }
    }
}

const char *game_menu_text(uint32_t id, const char *lang) {
    if (id < HM_TEXT_BASE || id >= T_END) return NULL;
    int l = 0;
    for (int i = 0; i < NLANG; i++)
        if (lang && !strcmp(lang, langs[i])) l = i;
    if (id < T_COUNT) return texts[id - HM_TEXT_BASE][l];
    int b = (int)(id - T_BIND_VALUE);
    if (!have_input()) return "-";
    if (input_capture_state() == b) return texts[T_CAPTURE - HM_TEXT_BASE][l];
    static __thread char buf[160];
    binding_text(b, l, buf, sizeof buf);
    return buf;
}

// ---- guest helpers
static uint64_t call1(Cpu *c, uint64_t fn, uint64_t a0) {
    c->x[0] = a0;
    guest_call(c, fn);
    return c->x[0];
}

static void row_refresh(Cpu *c, uint64_t row) {  // after a value change: the toggle constructor's own calls
    call1(c, LD64(LD64(row) + ROW_VT_REFRESH), row);
    c->x[1] = 0;
    call1(c, LD64(LD64(row) + ROW_VT_REFRESH2), row);
}

// ---- the rows
volatile int g_game_menu_fullscreen_req;  // (consumed on the window thread: runtime/ui/menu.cpp)
static uint64_t fullscreen_row;           // the current Options screen's (checked by label before use)

static void save(void) {
    if (!settings_save()) LOG("[game-menu] saving hylian-melodies.ini failed\n");
}

static void on_fullscreen(Cpu *c) {  // bound member function: x0 = object (unused), w1 = new value
    bool v = c->x[1] & 1;
    g_settings.fullscreen = v;
    settings_changed(SET_FULLSCREEN);
    save();
    g_game_menu_fullscreen_req = 1;
    LOG("[game-menu] fullscreen %s\n", v ? "on" : "off");
}

static void on_pacing(Cpu *c) {
    bool v = c->x[1] & 1;
    g_settings.frame_pacing = v;  // (read at every present: runtime/nvn/objects.c)
    settings_changed(SET_FRAME_PACING);
    save();
    LOG("[game-menu] frame pacing %s\n", v ? "on" : "off");
}

static uint64_t add_toggle(Cpu *c, uint64_t page, uint32_t label, bool value, const char *cb_name, HostFn cb) {
    uint64_t cb_addr = hle_register(cb_name, cb);  // (the same address for the same name)
    uint64_t sp0 = c->sp;
    c->sp -= 0x80;
    uint64_t key = c->sp, fn = c->sp + 0x20, slot = c->sp + 0x50;
    memset((void *)key, 0, 0x60);  // key: empty std::string (no config entry: the toggle then only calls back)
    ST64(fn + 0x00, LD64(G_BIND_VT_GOT) + 0x10);
    ST64(fn + 0x08, cb_addr);      // member function pointer: our host function
    ST64(fn + 0x10, 0);            // this-adjust 0, not virtual
    ST64(fn + 0x18, 0);            // bound object
    ST64(fn + 0x20, fn);           // std::function's callable: in its own buffer

    uint64_t row = call1(c, G_NEW, ROW_SIZE);
    c->x[0] = row; c->x[1] = label; c->x[2] = label + 1; c->x[3] = key; c->x[4] = fn;
    c->x[5] = value; c->x[6] = 0; c->x[7] = 0;
    guest_call(c, G_TOGGLE_CTOR);
    call1(c, LD64(LD64(fn) + 0x20), fn);  // the local std::function's destroy() (the row holds a copy)

    ST8(row + ROW_VALUE, value);  // (with an empty key the constructor starts it at "no")
    row_refresh(c, row);

    uint64_t end = LD64(page + 8), cap = LD64(page + 16);
    if (end < cap) {
        ST64(end, row);
        ST64(page + 8, end + 8);
    } else {
        ST64(slot, row);
        c->x[1] = slot;
        call1(c, G_VEC_PUSH_SLOW, page);
    }
    c->sp = sp0;
    return row;
}

#define G_CHOICE_CTOR    0x7000068410ull  // (row, label id, desc id, const std::string *key, const vector<Choice> *, std::function<void(std::string)> *, 0, 0)
#define G_STRFN_VT_GOT   0x7000a35010ull  // GOT slot: vtable of the bound member function the choice rows take
#define CHOICE_ROW_SIZE  0xc0
#define CHOICE_INDEX     0x88             // i32 current choice
// Choice (32 bytes): std::string value, i32 name text id, i32 description text id (-1: the row's own)

static void on_filter(Cpu *c) {  // x1 = the chosen value (std::string *, "0".."3")
    uint64_t s = c->x[1];
    const char *p = (const char *)(LD8(s) & 1 ? LD64(s + 16) : s + 1);
    int v = p[0] - '0';
    if (v < 0 || v > 3) return;
    g_settings.upscale_filter = v;  // (used from the next start: the renderer reads it once)
    settings_changed(SET_UPSCALE_FILTER);
    save();
    LOG("[game-menu] scaling filter %d (next start)\n", v);
}

static void push_row(Cpu *c, uint64_t page, uint64_t row, uint64_t slot) {  // (slot: 8 bytes of guest scratch)
    uint64_t end = LD64(page + 8), cap = LD64(page + 16);
    if (end < cap) {
        ST64(end, row);
        ST64(page + 8, end + 8);
    } else {
        ST64(slot, row);
        c->x[1] = slot;
        call1(c, G_VEC_PUSH_SLOW, page);
    }
}

static uint64_t add_choice(Cpu *c, uint64_t page, uint32_t label, uint32_t desc, const uint32_t *names, int n,
                           int value, const char *cb_name, HostFn cb, uint64_t obj) {
    uint64_t cb_addr = hle_register(cb_name, cb);
    uint64_t sp0 = c->sp;
    c->sp -= 0x100;
    uint64_t key = c->sp, fn = c->sp + 0x20, vec = c->sp + 0x50, slot = c->sp + 0x68, arr = c->sp + 0x70;
    memset((void *)key, 0, 0x100);
    if (n > 4) n = 4;
    for (int i = 0; i < n; i++) {  // value "i" (short string), its name
        ST8(arr + 32 * i, 1 << 1);
        ST8(arr + 32 * i + 1, '0' + i);
        ST32(arr + 32 * i + 0x18, names[i]);
        ST32(arr + 32 * i + 0x1c, 0xffffffffu);
    }
    ST64(vec, arr); ST64(vec + 8, arr + 32 * n); ST64(vec + 16, arr + 32 * n);
    ST64(fn + 0x00, LD64(G_STRFN_VT_GOT) + 0x10);
    ST64(fn + 0x08, cb_addr);
    ST64(fn + 0x18, obj);  // (our callback's x0)
    ST64(fn + 0x20, fn);

    uint64_t row = call1(c, G_NEW, CHOICE_ROW_SIZE);
    c->x[0] = row; c->x[1] = label; c->x[2] = desc; c->x[3] = key; c->x[4] = vec; c->x[5] = fn;
    c->x[6] = 0; c->x[7] = 0;
    guest_call(c, G_CHOICE_CTOR);
    call1(c, LD64(LD64(fn) + 0x20), fn);  // the local std::function's destroy() (the row holds a copy)

    ST32(row + CHOICE_INDEX, value >= 0 && value < n ? value : 0);
    row_refresh(c, row);
    push_row(c, page, row, slot);
    c->sp = sp0;
    return row;
}

// A button row (the main list's kind): A calls fn(obj, arg), a member function bound the way the game binds its own
// buttons (heap-held: it doesn't fit std::function's buffer). insert_at < 0: at the end.
#define G_BUTTON_CTOR    0x7000065f20ull  // (row, label id, desc id, std::function<void()> *, 0, 0)
#define G_BUTTONFN_VT_GOT 0x7000a34f70ull // GOT slot: vtable of the bound member function (with an int) buttons take
#define G_OPEN_PAGE_GOT  0x7000a34f78ull  // GOT slot: the Options screen's "open page <int>" member function
#define BUTTON_ROW_SIZE  0x60
static uint64_t add_button(Cpu *c, uint64_t page, uint32_t label, uint32_t desc, uint64_t fnaddr, uint64_t obj,
                           uint32_t arg, int insert_at) {
    uint64_t sp0 = c->sp;
    c->sp -= 0x40;
    uint64_t fn = c->sp, slot = c->sp + 0x30;
    memset((void *)fn, 0, 0x40);
    uint64_t f = call1(c, G_NEW, 0x28);
    ST64(f + 0x00, LD64(G_BUTTONFN_VT_GOT) + 0x10);
    ST64(f + 0x08, fnaddr);
    ST64(f + 0x10, 0);
    ST64(f + 0x18, obj);
    ST32(f + 0x20, arg);
    ST64(fn + 0x20, f);

    uint64_t row = call1(c, G_NEW, BUTTON_ROW_SIZE);
    c->x[0] = row; c->x[1] = label; c->x[2] = desc; c->x[3] = fn; c->x[4] = 0; c->x[5] = 0;
    guest_call(c, G_BUTTON_CTOR);
    call1(c, LD64(LD64(f) + 0x28), f);  // the local function's destroy_deallocate() (the row holds a copy)
    push_row(c, page, row, slot);
    uint64_t b = LD64(page), e = LD64(page + 8);
    if (insert_at >= 0 && b + 8 * (uint64_t)insert_at < e - 8) {  // move it up to insert_at
        for (uint64_t q = e - 8; q > b + 8 * (uint64_t)insert_at; q -= 8) ST64(q, LD64(q - 8));
        ST64(b + 8 * (uint64_t)insert_at, row);
    }
    c->sp = sp0;
    return row;
}

// ---- the Controls page
#define G_PAGES_PUSH_SLOW 0x7000014260ull  // vector<vector<unique_ptr<Row>>>::push_back slow path (pages, vector *)
#define SCREEN_SELECTED   0xc0             // i32: the selected row of the open page
#define SCREEN_PAGE_INDEX 0xc4             // i32: the open page
#define LABEL_CHANGE_CONTROLLERS 177       // the main list's "Change Controllers" (the console's controller applet)
#define ROW_VT_DELETE     0x08             // a row's deleting destructor (what its unique_ptr calls)
static int controls_main_row = -1;         // where our Controls button sits in the main list
enum { NBUTTONS = 16 };
static uint64_t bind_rows[NBUTTONS];
static unsigned bind_row_gen[NBUTTONS];
static int controls_page = -1;

static void on_bind_choice(Cpu *c) {  // left / right on a binding row: x0 = the button
    if (input_capture_state() < 0) input_capture_begin((int)c->x[0]);
}

static void on_reset(Cpu *c) {
    (void)c;
    input_bindings_reset();
    save();
}

static void add_controls_page(Cpu *c, uint64_t self) {
    uint64_t sp0 = c->sp;
    c->sp -= 0x40;
    uint64_t vec = c->sp, slot = c->sp + 0x20;
    memset((void *)vec, 0, 0x40);  // the new page's row vector (moved into the screen's page list below)
    unsigned gen = input_bindings_generation();
    for (int b = 0; b < NBUTTONS; b++) {
        uint32_t name = T_BIND_VALUE + b;
        bind_rows[b] = add_choice(c, vec, T_BIND_LABEL + b, T_BIND_DESC, &name, 1, 0, "hm_game_menu_bind", on_bind_choice, b);
        bind_row_gen[b] = gen;
    }
    add_button(c, vec, T_RESET, T_RESET_DESC, hle_register("hm_game_menu_reset", on_reset), 0, 0, -1);
    uint64_t pages = self + SCREEN_PAGES;
    uint64_t end = LD64(pages + 8), cap = LD64(pages + 16);
    controls_page = (int)((end - LD64(pages)) / 24);
    if (end < cap) {
        memcpy((void *)end, (void *)vec, 24);
        ST64(pages + 8, end + 24);
    } else {
        c->x[1] = vec;
        call1(c, G_PAGES_PUSH_SLOW, pages);
        if (LD64(vec)) call1(c, G_DELETE, LD64(vec));  // (what a moved-from vector still holds: nothing, normally)
    }
    // our button takes the place of Change Controllers (no use on a PC): the same row index, so the game's Back from
    // its own pages (main row = page number) still lands right; Back from ours is put right in the layout hook
    uint64_t main = LD64(pages);
    uint64_t row = add_button(c, main, T_CONTROLS, T_CONTROLS_DESC, LD64(G_OPEN_PAGE_GOT), self, (uint32_t)controls_page,
                              -1);
    uint64_t mb = LD64(main), me = LD64(main + 8);
    controls_main_row = (int)((me - mb) / 8) - 1;
    for (uint64_t q = mb; q < me - 8; q += 8) {
        uint64_t old = LD64(q);
        if (LD32(old + ROW_LABEL) != LABEL_CHANGE_CONTROLLERS) continue;
        ST64(q, row);
        ST64(main + 8, me - 8);  // (the button's own slot at the end goes)
        call1(c, LD64(LD64(old) + ROW_VT_DELETE), old);
        controls_main_row = (int)((q - mb) / 8);
        break;
    }
    (void)slot;
    c->sp = sp0;
}

// Selected binding row, every frame (the choice row's input method): A starts waiting for the new key or button.
void hm_hook_choice_input(Cpu *c, GuestFn orig) {
    extern volatile uint64_t g_input_buttons;  // (what the game sees: runtime/hle/input.c)
    extern uint64_t renderer_present_count(void);
    static uint64_t was, last_row, last_frame;
    uint64_t row = c->x[0], now = g_input_buttons, frame = renderer_present_count();
    // (a press only counts on a row that was already selected the frame before: the A that opened the page, or
    // that's still held after a capture, doesn't start one)
    bool fresh = row != last_row || frame > last_frame + 2;
    bool a_pressed = !fresh && (now & 1) && !(was & 1);
    was = now, last_row = row, last_frame = frame;
    if (have_input() && a_pressed && input_capture_state() < 0)
        for (int b = 0; b < NBUTTONS; b++)
            if (bind_rows[b] == row && LD32(row + ROW_LABEL) == (uint32_t)(T_BIND_LABEL + b)) {
                input_capture_begin(b);
                return;  // (the press is ours)
            }
    orig(c);
}

// Every choice row on the open page, every frame (its "set y"): binding rows redraw after a change.
void hm_hook_choice_update(Cpu *c, GuestFn orig) {
    uint64_t row = c->x[0];
    if (have_input()) {
        unsigned gen = input_bindings_generation();
        for (int b = 0; b < NBUTTONS; b++)
            if (bind_rows[b] == row && bind_row_gen[b] != gen && LD32(row + ROW_LABEL) == (uint32_t)(T_BIND_LABEL + b)) {
                uint64_t saved[13], regs[8];
                memcpy(saved, &c->x[19], sizeof saved);
                memcpy(regs, &c->x[0], sizeof regs);
                bind_row_gen[b] = gen;
                row_refresh(c, row);
                memcpy(&c->x[19], saved, sizeof saved);
                memcpy(&c->x[0], regs, sizeof regs);
            }
    }
    orig(c);
}

// The Options screen's "open page <x1>" (also the game's Back to the main list, after it set the selected row to the
// page number it leaves): leaving our Controls page selects our button's own row, so the cursor lands on it.
void hm_hook_options_open_page(Cpu *c, GuestFn orig) {  // x0 = the screen, w1 = the page
    uint64_t self = c->x[0];
    if ((uint32_t)c->x[1] == 0 && controls_page > 0 && controls_main_row >= 0 &&
        (int32_t)LD32(self + SCREEN_PAGE_INDEX) == controls_page)
        ST32(self + SCREEN_SELECTED, (uint32_t)controls_main_row);
    orig(c);
}

// ---- the pause menu (one screen object; its rows are text elements in fixed fields, picked by an index):
// Leaderboards (online only) becomes "Save and Return to Title" and runs the game's Save and Quit (which goes to the
// title); Save and Quit keeps its label and also closes the game once the save is written (runtime/ui/menu.c). Both
// ask first: the first A shows "Are you sure?" in the description box, a second A on the same row goes ahead, moving
// away (or leaving the menu) cancels.
#define TEXT_LEADERBOARDS 103             // the pause menu's Leaderboards label
#define PAUSE_DESC        0x48            // the description box element
#define PAUSE_SELECTED    0x104           // i32: 0 Return, 1 Options, 2 Achievements, 3 Leaderboards, 4 Save and Quit
#define PAUSE_SUBMENU     0x118           // u8: the leaderboard kinds are shown instead
#define PAUSE_ROW_TITLE   3
#define PAUSE_ROW_QUIT    4
#define G_PAUSE_DESCRIBE  0x700006a9a0ull // (screen): the description for the selected row (hooked below)
#define G_DESC_SET        0x700024c4c0ull // (description box, text id)
volatile uint64_t g_game_menu_quit_req, g_game_menu_quit_commits;  // (runtime/ui/menu.c)
static uint64_t pause_pending_obj;
static int pause_pending = -1;

static bool disabled(void);

void hm_hook_pause_describe(Cpu *c, GuestFn orig) {  // x0 = the pause screen
    uint64_t self = c->x[0];
    int sel = (int32_t)LD32(self + PAUSE_SELECTED);
    if (disabled() || LD8(self + PAUSE_SUBMENU) || (sel != PAUSE_ROW_TITLE && sel != PAUSE_ROW_QUIT)) { orig(c); return; }
    bool ask = pause_pending == sel && pause_pending_obj == self;
    c->x[0] = LD64(self + PAUSE_DESC);
    c->x[1] = sel == PAUSE_ROW_TITLE ? (ask ? T_CONFIRM_TITLE : T_PAUSE_TITLE_DESC) : (ask ? T_CONFIRM_QUIT : T_PAUSE_QUIT_DESC);
    guest_call(c, G_DESC_SET);
}

// The game's UI sounds: its play function with a sound's name, read from the game's own data where its code builds
// that name (the names stay out of this repository).
#define G_PLAY_SOUND      0x7000001710ull // (const std::string *name, 0, 0, std::string *out, d0..d5)
#define G_SOUND_SELECT    0x70008cab9full // what A on a menu row plays (NUL-terminated, as each below)
#define G_SOUND_MOVE      0x70008b0637ull // the title screen's left / right
#define G_SOUND_QUIT      0x70008a4d65ull // the pause menu's Save and Quit, once confirmed
static void play_sound(Cpu *c, uint64_t name_addr) {
    uint64_t saved[13], regs[8];
    __uint128_t vregs[6];
    memcpy(saved, &c->x[19], sizeof saved);
    memcpy(regs, &c->x[0], sizeof regs);
    memcpy(vregs, c->v, sizeof vregs);
    uint64_t sp0 = c->sp;
    c->sp -= 0x40;
    uint64_t name = c->sp, out = c->sp + 0x20, buf = 0;
    memset((void *)name, 0, 0x40);
    size_t n = strnlen((const char *)name_addr, 64);
    if (n <= 22) {  // libc++ std::string: short form in place, else a buffer from the game's allocator
        ST8(name, n << 1);
        memcpy((void *)(name + 1), (const void *)name_addr, n);
    } else {
        buf = call1(c, G_NEW, (n + 16) & ~15ull);
        memcpy((void *)buf, (const void *)name_addr, n);
        ST8(buf + n, 0);
        ST64(name, ((n + 16) & ~15ull) | 1);
        ST64(name + 8, n);
        ST64(name + 16, buf);
    }
    c->x[0] = name; c->x[1] = 0; c->x[2] = 0; c->x[3] = out;
    c->v[0] = c->v[3] = 0x3ff0000000000000ull;  // (as the game passes them: 1.0, 0, 0, 1.0, 0, 0)
    c->v[1] = c->v[2] = c->v[4] = c->v[5] = 0;
    guest_call(c, G_PLAY_SOUND);
    if (LD8(out) & 1) call1(c, G_DELETE, LD64(out + 16));
    if (buf) call1(c, G_DELETE, buf);
    c->sp = sp0;
    memcpy(&c->x[19], saved, sizeof saved);
    memcpy(&c->x[0], regs, sizeof regs);
    memcpy(c->v, vregs, sizeof vregs);
}

static void pause_describe(Cpu *c, uint64_t self) {
    uint64_t saved[13], regs[8];
    memcpy(saved, &c->x[19], sizeof saved);
    memcpy(regs, &c->x[0], sizeof regs);
    call1(c, G_PAUSE_DESCRIBE, self);
    memcpy(&c->x[19], saved, sizeof saved);
    memcpy(&c->x[0], regs, sizeof regs);
}

void hm_hook_pause_update(Cpu *c, GuestFn orig) {  // x0 = the pause screen, every frame while it's open
    extern volatile uint64_t g_input_buttons;  // (what the game sees: runtime/hle/input.c)
    extern uint64_t renderer_present_count(void);
    extern volatile uint64_t g_save_commits;
    static uint64_t was, last_frame;
    uint64_t self = c->x[0], now = g_input_buttons, frame = renderer_present_count();
    bool fresh = frame > last_frame + 2;  // (the menu wasn't open: a held A is no press, a pending question goes)
    bool a = !fresh && (now & 1) && !(was & 1);
    was = now, last_frame = frame;
    if (disabled()) { orig(c); return; }
    int sel = (int32_t)LD32(self + PAUSE_SELECTED);
    bool sub = LD8(self + PAUSE_SUBMENU) != 0;
    if (pause_pending >= 0 && (fresh || self != pause_pending_obj || sel != pause_pending || sub)) {
        pause_pending = -1;  // moved away: no longer asked
        if (!fresh && self == pause_pending_obj && !sub) pause_describe(c, self);
    }
    if (a && !sub && (sel == PAUSE_ROW_TITLE || sel == PAUSE_ROW_QUIT)) {
        if (pause_pending == sel && pause_pending_obj == self) {  // confirmed: the game's own Save and Quit runs
            pause_pending = -1;
            ST32(self + PAUSE_SELECTED, PAUSE_ROW_QUIT);
            if (sel == PAUSE_ROW_QUIT) {
                struct timespec ts;
                clock_gettime(CLOCK_MONOTONIC, &ts);
                g_game_menu_quit_commits = g_save_commits;
                g_game_menu_quit_req = (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
            }
            LOG("[game-menu] pause: save and %s\n", sel == PAUSE_ROW_QUIT ? "quit" : "return to the title");
            orig(c);
            return;
        }
        pause_pending = sel, pause_pending_obj = self;  // first A: ask (the game doesn't see this press)
        play_sound(c, G_SOUND_SELECT);
        pause_describe(c, self);
        return;
    }
    orig(c);
}

// ---- the title screen: an Exit button beside the gear (the port's own art, packaging/art/exit-button.png)
// The title screen object: +0x70/+0x78/+0x80 Continue / New Game / New Game 2P, +0x88 the gear (an icon button: a
// sprite in the game's button frame), +0x90 an eShop button the game shows only in a mode this port never has (its
// GOT slot 0x7000a34a90 -> a byte, off here), +0xbc the main column's row, +0xc0 the column: 0 gear, 1 eShop, 2 the main column (left / right skip
// 1 while the flag is off; A acts on the column). Our icon button takes the eShop's place (the eShop button goes
// whatever the flag: no use here): our layout hook puts it where the gear was and the gear to its right (owner),
// our update hook makes left / right go Exit - gear - main column and acts on A on Exit.
#include "bntx.h"
#include "exit_icon.h"
#define G_SPRITE_CTOR     0x700022f170ull // (sprite (0x1b0 bytes), const std::string *texture name)
#define G_ICON_BUTTON_CTOR 0x700024b940ull // (button (0x80 bytes), sprite, 0x1d60, 0x1e): what the gear is
#define G_ACTION_PRESSED  0x700040ebd0ull // (action, -1, 0) -> pressed this frame
#define TITLE_GEAR        0x88
#define TITLE_ESHOP       0x90
#define TITLE_COLUMN      0xc0
#define TITLE_BUSY        0x14c           // i32 > 0: the menu doesn't take input yet
#define ELEM_VT_PLACE     0x10            // (element, x, y, width), 640x360 units
#define G_SCREEN_ACTIVE   0x700000d070ull // (screen) -> the screen is the one on top (the layout's own check)
#define ACT_LEFT1 0x50
#define ACT_LEFT2 0x5c
#define ACT_RIGHT1 0x4f
#define ACT_RIGHT2 0x5e
#define ACT_OK1 0x28
#define ACT_OK2 0x0e
#define EXIT_TEXTURE      "gui/HM_ExitButton.png"  // -> data:/textures_bin/gui/HM_ExitButton.bntx (ours, in memory)
volatile int g_game_menu_quit_now;        // (runtime/ui/menu.c closes the window)
static uint64_t exit_button, exit_screen;

static bool disabled(void);

int game_menu_romfs_extras(const RomfsExtraFile **extra) {
    static uint8_t bntx[BNTX_RGBA32_SIZE];
    static RomfsExtraFile files[1];
    if (!bntx_rgba32("HM_ExitButton", hm_exit_icon, bntx)) return 0;
    files[0] = (RomfsExtraFile){"textures_bin/gui/HM_ExitButton.bntx", bntx, sizeof bntx};
    *extra = files;
    return 1;
}

void hm_hook_title_build(Cpu *c, GuestFn orig) {  // x0 = the title screen
    uint64_t self = c->x[0];
    orig(c);
    if (disabled()) return;
    uint64_t saved[13], r0 = c->x[0];
    memcpy(saved, &c->x[19], sizeof saved);
    uint64_t sp0 = c->sp;
    c->sp -= 0x20;
    uint64_t name = c->sp;
    memset((void *)name, 0, 0x20);
    size_t n = strlen(EXIT_TEXTURE);  // (21: a short string)
    ST8(name, n << 1);
    memcpy((void *)(name + 1), EXIT_TEXTURE, n);
    uint64_t sprite = call1(c, G_NEW, 0x1b0);
    c->x[0] = sprite; c->x[1] = name;
    guest_call(c, G_SPRITE_CTOR);
    uint64_t button = call1(c, G_NEW, 0x80);
    c->x[0] = button; c->x[1] = sprite; c->x[2] = 0x1d60; c->x[3] = 0x1e;
    guest_call(c, G_ICON_BUTTON_CTOR);
    uint64_t old = LD64(self + TITLE_ESHOP);
    ST64(self + TITLE_ESHOP, button);
    if (old) call1(c, LD64(LD64(old) + ROW_VT_DELETE), old);
    exit_button = button, exit_screen = self;
    c->sp = sp0;
    memcpy(&c->x[19], saved, sizeof saved);
    c->x[0] = r0;
    LOG("[game-menu] title screen %llx: Exit button added\n", (unsigned long long)self);
}

void hm_hook_title_layout(Cpu *c, GuestFn orig) {  // x0 = the title screen, every frame
    uint64_t self = c->x[0];
    if (self != exit_screen || LD64(self + TITLE_ESHOP) != exit_button) { orig(c); return; }
    // Placing an element draws it this frame. The game draws the gear at (20, 306), 31 wide, and the eShop field only
    // in its eShop mode: with the two fields swapped for its layout it draws Exit there; the gear goes to its right.
    uint64_t gear = LD64(self + TITLE_GEAR);
    ST64(self + TITLE_GEAR, exit_button);
    ST64(self + TITLE_ESHOP, gear);
    orig(c);
    ST64(self + TITLE_GEAR, gear);
    ST64(self + TITLE_ESHOP, exit_button);
    uint64_t saved[13], regs[8];
    memcpy(saved, &c->x[19], sizeof saved);
    memcpy(regs, &c->x[0], sizeof regs);
    if (call1(c, G_SCREEN_ACTIVE, self) & 1) {  // (only while the game draws its own buttons: not under the gear's menu)
        c->x[0] = gear; c->x[1] = 56; c->x[2] = 306; c->x[3] = 31;
        guest_call(c, LD64(LD64(gear) + ELEM_VT_PLACE));
    }
    memcpy(&c->x[19], saved, sizeof saved);
    memcpy(&c->x[0], regs, sizeof regs);
}

static bool action(Cpu *c, uint32_t a1, uint32_t a2) {
    uint64_t saved[13], regs[8];
    memcpy(saved, &c->x[19], sizeof saved);
    memcpy(regs, &c->x[0], sizeof regs);
    c->x[0] = a1; c->x[1] = 0xffffffffu; c->x[2] = 0;
    guest_call(c, G_ACTION_PRESSED);
    bool r = c->x[0] & 1;
    if (!r) {
        c->x[0] = a2; c->x[1] = 0xffffffffu; c->x[2] = 0;
        guest_call(c, G_ACTION_PRESSED);
        r = c->x[0] & 1;
    }
    memcpy(&c->x[19], saved, sizeof saved);
    memcpy(&c->x[0], regs, sizeof regs);
    return r;
}

void hm_hook_title_update(Cpu *c, GuestFn orig) {  // x0 = the title screen, every frame
    uint64_t self = c->x[0];
    if (self != exit_screen || LD64(self + TITLE_ESHOP) != exit_button || g_game_menu_quit_now) {
        orig(c);
        return;
    }
    int col = (int32_t)LD32(self + TITLE_COLUMN);
    bool ready = (int32_t)LD32(self + TITLE_BUSY) <= 0;
    bool left = ready && action(c, ACT_LEFT1, ACT_LEFT2), right = ready && action(c, ACT_RIGHT1, ACT_RIGHT2);
    // On screen, left to right: Exit (our column 1), the gear (0), the main column (2). The game moves 2 -> 0 on left
    // and 0 -> 2 on right by itself (it skips 1); the rest is ours.
    if (col == 1 && ready) {
        if (action(c, ACT_OK1, ACT_OK2)) {  // Exit: the game's own close sound, then the window closes
            play_sound(c, G_SOUND_SELECT);
            play_sound(c, G_SOUND_QUIT);
            g_game_menu_quit_now = 1;
            LOG("[game-menu] title screen: exit\n");
            return;  // (the game doesn't see this press)
        }
        if (left) return;  // (nothing further left; the game would move to the gear)
    }
    orig(c);
    int now = (int32_t)LD32(self + TITLE_COLUMN);
    if (col == 0 && left && now == 0) ST32(self + TITLE_COLUMN, 1), play_sound(c, G_SOUND_MOVE);  // gear -> Exit
    else if (col == 1 && right) ST32(self + TITLE_COLUMN, 0);  // Exit -> gear (the game moved to 2, with its sound)
}

static bool disabled(void) {
    const char *e = getenv("HM_GAME_MENU");
    return e && !strcmp(e, "0");
}

void hm_hook_options_build(Cpu *c, GuestFn orig) {
    uint64_t self = c->x[0];
    orig(c);
    if (disabled()) return;
    uint64_t saved[13];
    memcpy(saved, &c->x[19], sizeof saved);  // x19..x30 and the return value stay the caller's
    uint64_t r0 = c->x[0];
    uint64_t b = LD64(self + SCREEN_PAGES), e = LD64(self + SCREEN_PAGES + 8);
    int added = 0;
    for (uint64_t page = b; page < e; page += 24) {
        uint64_t rb = LD64(page), re = LD64(page + 8);
        if (rb == re || LD32(LD64(rb) + ROW_LABEL) != LABEL_DISCO) continue;
        fullscreen_row = add_toggle(c, page, T_FULLSCREEN, g_settings.fullscreen, "hm_game_menu_fullscreen", on_fullscreen);
        add_toggle(c, page, T_PACING, g_settings.frame_pacing, "hm_game_menu_pacing", on_pacing);
        static const uint32_t filters[] = {T_SHARP, T_SMOOTH, T_NEAREST, T_PIXEL};  // (upscale_filter 0..3)
        add_choice(c, page, T_FILTER, T_FILTER_DESC, filters, 4, g_settings.upscale_filter, "hm_game_menu_filter",
                   on_filter, 0);
        // ours first: the three rows just appended move to the top of the page
        rb = LD64(page), re = LD64(page + 8);
        uint64_t ours[3];
        for (int i = 0; i < 3; i++) ours[i] = LD64(re - 24 + 8 * i);
        for (uint64_t q = re - 8; q >= rb + 24; q -= 8) ST64(q, LD64(q - 24));
        for (int i = 0; i < 3; i++) ST64(rb + 8 * i, ours[i]);
        added = 1;
        break;
    }
    if (added && have_input()) add_controls_page(c, self);
    LOG("[game-menu] options screen %llx: %s; Controls page %d at main row %d\n", (unsigned long long)self,
        added ? "rows added to Graphics" : "Graphics page not found", controls_page, controls_main_row);
    memcpy(&c->x[19], saved, sizeof saved);
    c->x[0] = r0;
}

void hm_hook_toggle_update(Cpu *c, GuestFn orig) {  // x0 = row, every frame for each toggle on the open page
    uint64_t row = c->x[0];
    if (row == fullscreen_row && LD32(row + ROW_LABEL) == T_FULLSCREEN &&
        (LD8(row + ROW_VALUE) & 1) != g_settings.fullscreen) {  // F11 / Alt+Enter switched meanwhile
        uint64_t saved[13], regs[8];
        memcpy(saved, &c->x[19], sizeof saved);
        memcpy(regs, &c->x[0], sizeof regs);
        ST8(row + ROW_VALUE, g_settings.fullscreen);
        row_refresh(c, row);
        memcpy(&c->x[19], saved, sizeof saved);
        memcpy(&c->x[0], regs, sizeof regs);  // (the update's own arguments)
    }
    orig(c);
}

// ---- layout
// The Options screen's per-frame layout of the open page (640x360 units): visible rows (byte +0x2c) 30 apart, the block
// centred on y = 183, the panel 17 above the first row and 18 taller than the rows. The game's pages have at most 8
// rows; more run into the title and the description box (about y 35..303 is free), so longer pages get a tighter
// pitch, centred in that space. Pages of 8 or fewer keep the game's own layout.
#define SCREEN_WIDE       0xc8  // u8: panel 408 wide, else 328
#define SCREEN_PANEL      0x28  // the panel element (set by G_PANEL_SET)
#define ROW_VISIBLE       0x2c  // u8
#define ROW_VT_SET_Y      0x20  // (row, y)
#define G_LAYOUT_PRE1     0x700024c890ull  // (the layout's first calls, on the elements at screen +0x10 and +0x18)
#define G_LAYOUT_PRE2     0x700024c580ull
#define G_PANEL_SET       0x700024ad90ull  // (panel, x, y, w, h, 0, 0, 1)
#define FREE_TOP          35
#define FREE_BOTTOM       303
#define SCROLL_ROWS       9
#define OFF_SCREEN_Y      1000

void hm_hook_options_layout(Cpu *c, GuestFn orig) {  // x0 = the Options screen
    uint64_t self = c->x[0];
    uint64_t page = LD64(self + SCREEN_PAGES) + (int64_t)(int32_t)LD32(self + SCREEN_PAGE_INDEX) * 24;
    uint64_t rb = LD64(page), re = LD64(page + 8);
    int n = 0;
    for (uint64_t r = rb; r < re; r += 8) n += LD8(LD64(r) + ROW_VISIBLE);
    if (n <= 8) { orig(c); return; }
    uint64_t saved[13];
    memcpy(saved, &c->x[19], sizeof saved);
    // up to 10 rows: all shown, closer together; more: a window of SCROLL_ROWS that follows the selected row (the
    // rest are moved off the screen)
    int shown = n > 10 ? SCROLL_ROWS : n;
    static int first, page_was = -1;
    int page_i = (int32_t)LD32(self + SCREEN_PAGE_INDEX), sel = (int32_t)LD32(self + 0xc0);
    if (page_i != page_was) first = 0, page_was = page_i;
    if (sel < first) first = sel;
    if (sel >= first + shown) first = sel - shown + 1;
    if (first > n - shown) first = n - shown;
    if (first < 0) first = 0;
    int pitch = (FREE_BOTTOM - FREE_TOP - 18) / shown;
    if (pitch > 30) pitch = 30;
    int h = shown * pitch;
    int top = (FREE_TOP + FREE_BOTTOM) / 2 + 17 - (h + 18) / 2;  // (panel centred in the free space)
    call1(c, G_LAYOUT_PRE1, LD64(self + 0x10));
    call1(c, G_LAYOUT_PRE2, LD64(self + 0x18));
    int i = 0;
    for (uint64_t r = rb; r < re; r += 8) {
        uint64_t row = LD64(r);
        if (!LD8(row + ROW_VISIBLE)) continue;
        int k = i++ - first;
        c->x[1] = (uint32_t)(k >= 0 && k < shown ? top - 5 + k * pitch : OFF_SCREEN_Y);
        call1(c, LD64(LD64(row) + ROW_VT_SET_Y), row);
    }
    int w = LD8(self + SCREEN_WIDE) ? 408 : 328;
    c->x[0] = self + SCREEN_PANEL;
    c->x[1] = (uint32_t)((640 - w) / 2); c->x[2] = (uint32_t)(top - 17); c->x[3] = (uint32_t)w;
    c->x[4] = (uint32_t)(h + 18); c->x[5] = 0; c->x[6] = 0; c->x[7] = 1;
    guest_call(c, G_PANEL_SET);
    memcpy(&c->x[19], saved, sizeof saved);
}

// ---- text
// The text lookup's result: {i32 style (-1: no such text); std::u32string text at +8}. libc++ u32string: short form
// (first byte = length << 1, up to 4 characters at +4) or long form (capacity | 1, length, buffer from the game's
// allocator, which the game's destructor frees).
static size_t utf8_decode(const char *s, uint32_t *out) {  // out may be NULL (count only)
    size_t n = 0;
    for (const unsigned char *p = (const unsigned char *)s; *p;) {
        uint32_t cp = *p++;
        int more = cp >= 0xF0 ? 3 : cp >= 0xE0 ? 2 : cp >= 0xC0 ? 1 : 0;
        if (more) cp &= 0x3F >> more;
        while (more-- && (*p & 0xC0) == 0x80) cp = cp << 6 | (*p++ & 0x3F);
        if (out) out[n] = cp;
        n++;
    }
    return n;
}

static void put_u32string(Cpu *c, uint64_t s, const char *t) {
    if (LD8(s) & 1) call1(c, G_DELETE, LD64(s + 16));
    size_t n = utf8_decode(t, NULL);
    memset((void *)s, 0, 24);
    uint64_t d = s + 4;
    if (n > 4) {
        uint64_t cap = (n + 4) & ~3ull;  // elements, room for the terminator
        d = call1(c, G_NEW, cap * 4);
        ST64(s, cap | 1);
        ST64(s + 8, n);
        ST64(s + 16, d);
    } else {
        ST8(s, n << 1);
    }
    utf8_decode(t, (uint32_t *)d);
    ST32(d + 4 * n, 0);
}

static void read_string(uint64_t s, char *out, size_t cap) {  // libc++ std::string -> C string (truncated)
    size_t n = LD8(s) & 1 ? LD64(s + 8) : LD8(s) >> 1;
    const char *p = (const char *)(LD8(s) & 1 ? LD64(s + 16) : s + 1);
    if (n >= cap) n = cap - 1;
    memcpy(out, p, n);
    out[n] = 0;
}

void hm_hook_text_lookup(Cpu *c, GuestFn orig) {  // w0 = id, x1 = language (std::string *, in/out), x8 = result
    uint32_t game_id = (uint32_t)c->x[0], id = game_id;
    if (game_id == TEXT_LEADERBOARDS && !disabled()) id = T_PAUSE_TITLE;  // (the pause menu's row, repurposed)
    if (id < HM_TEXT_BASE || id >= T_END) { orig(c); return; }
    uint64_t res = c->x[8], lang_s = c->x[1];
    if (id == game_id)  // ours: a game text of the same kind, for the style field (a game's own id keeps its own)
        c->x[0] = id >= T_COUNT ? TEXT_CHOICE : text_style[id - HM_TEXT_BASE];
    orig(c);                                  // the text is replaced
    char lang[16];
    read_string(lang_s, lang, sizeof lang);  // (the lookup fills in the game's current language when it was empty)
    uint64_t saved[13];
    memcpy(saved, &c->x[19], sizeof saved);
    put_u32string(c, res + 8, game_menu_text(id, lang));
    memcpy(&c->x[19], saved, sizeof saved);
    static char logged[16];
    if (strcmp(logged, lang)) {
        LOG("[game-menu] text language \"%s\"\n", lang);
        memcpy(logged, lang, sizeof logged);
    }
}
