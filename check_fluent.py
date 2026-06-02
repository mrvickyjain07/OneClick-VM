"""Quick check of available qfluentwidgets components"""
try:
    from qfluentwidgets import (
        FluentWindow, NavigationItemPosition, NavigationPushButton,
        ScrollArea, CardWidget, SimpleCardWidget,
        PushButton, PrimaryPushButton, TransparentPushButton,
        ComboBox, Slider, SpinBox, ProgressBar,
        SubtitleLabel, BodyLabel, TitleLabel, CaptionLabel, StrongBodyLabel,
        Theme, setTheme, setThemeColor,
        InfoBadge, InfoLevel,
        SmoothScrollArea,
        FluentIcon as FIF,
        LineEdit, TextEdit, PlainTextEdit,
        TransparentToolButton,
        ToolButton,
        HorizontalSeparator,
        ProgressRing,
        IndeterminateProgressRing,
        GroupHeaderCardWidget,
        ExpandGroupSettingCard,
        SettingCardGroup,
        SwitchSettingCard,
        PushSettingCard,
        ColorSettingCard,
        ComboBoxSettingCard,
        RangeSettingCard,
        OptionsSettingCard,
    )
    print("All imports OK!")
    print(dir(FIF)[:20])
except ImportError as e:
    print(f"Import error: {e}")
    # Try basic import
    import qfluentwidgets
    print(dir(qfluentwidgets))
