from worlds.LauncherComponents import Component, Type, components, launch as launch_component

from .world import MassEffectLE1World as MassEffectLE1World


def launch_client(*args: str) -> None:
    from .client import launch
    launch_component(launch, name="ME1Client", args=args)


components.append(Component("Mass Effect LE1 Client", func=launch_client, component_type=Type.CLIENT,
                            game_name="Mass Effect Legendary Edition 1", supports_uri=True,
                            description="Connects Mass Effect Legendary Edition 1 (LE1APBridge) to a multiworld."))
