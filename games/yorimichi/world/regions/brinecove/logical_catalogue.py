"""Explicit coastal ownership shared by the recipe and source-data consumers."""
COMPONENTS = (
    ('Rocks', 'terrain_dressing'), ('Harbor', 'harbor'), ('TownLower', 'lower_town'),
    ('Market', 'market'), ('TownUpper', 'upper_town'), ('Landmarks', 'landmarks'),
    ('Ships', 'ships'), ('Props', 'props'), ('Understory', 'vegetation'),
)
HEROES = ('pirate-queen-statue', 'galleon-hull', 'harbor-capstan')
PARENTS = tuple('SM_BC_' + key for key, _ in COMPONENTS) + ('SM_BC_Ground',) + tuple(
    'SM_BC_Hero_' + ''.join(part.title() for part in slug.split('-')) for slug in HEROES)
