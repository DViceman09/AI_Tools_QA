from __future__ import annotations


SUPPORTED_GAME_PLATFORMS = ("mobile", "pc", "console")
SUPPORTED_ENGINES = ("Unity", "Unreal", "Custom", "Other")

GAME_COMPONENTS = (
    "gameplay",
    "ui_ux",
    "rendering",
    "performance",
    "networking",
    "platform_compliance",
    "input_controls",
    "save_progression",
    "commerce_liveops",
    "build_release",
    "audio",
)

COMPONENT_OWNER_MAPPING = {
    "gameplay": "Gameplay",
    "ui_ux": "UI/UX",
    "rendering": "Graphics",
    "performance": "Core Tech",
    "networking": "Online Services",
    "platform_compliance": "Platform",
    "input_controls": "Gameplay",
    "save_progression": "Core Tech",
    "commerce_liveops": "LiveOps",
    "build_release": "Release Engineering",
    "audio": "Audio",
}

GAME_SCOPE_SUMMARY = "Scope: mobile, PC, and console games only."

