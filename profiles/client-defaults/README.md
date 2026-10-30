# DJ2 client defaults

`dj2.json` is the `launch.client_defaults` fragment for the signed DJ2 release.
Merge it into the local launch-profile JSON before `omk release pack`; populate
`servers` with the actual compatible server when its address exists. No public
server address is configured yet. The release signature covers this fragment.

JourneyMap 1.12.2 5.7.1p3 uses the 5.7 config directory. Initial primary minimap
is square, top-right, with no grid; full map also has no grid. These two configs
are copied from the owner's archived client; maps, waypoints, worlds and account
files are excluded. Each config is seeded only when absent. Player changes are
never overwritten, including after pack upgrades. The secondary minimap retains
JourneyMap defaults. The launcher explicitly allowlists these JSON settings paths;
adding other formats/versions requires a small adapter change and tests.

Original config SHA256 (before stripping comments):

- `journeymap.minimap.config`: `2f6547ec4c7f641c8c8b0ab253be1ff38fe772623face15aa47ae4704818fc20`
- `journeymap.fullmap.config`: `d806478e5ae5ded9e595197bf62d31a3d147596e6781cbc3940b6ea18b7fa1c1`
