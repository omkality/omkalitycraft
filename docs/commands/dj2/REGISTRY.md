# Полный реестр серверных команд DJ2

Снимок зарегистрированных команд Forge 1.12.2 / DJ2 RU 2.21.3 от 2026-10-30.
Всего **438 записей**, включая обнаруженные подкоманды Forge CommandTree.
Это факт регистрации, а не отметка успешного выполнения каждой команды.

[Назад к практическому справочнику](README.md). [Исходные метаданные](registry.json).

Уровень 0 обычно означает доступ обычному игроку; 1–4 — уровни OP Minecraft.
Отдельные реализации дополнительно проверяют владельца/измерение/предмет/право;
FTB-ranks может переопределить доступ по точному node. `—` означает, что уровень
не получен стандартным методом. Не выдавайте права только по этой колонке.
У корневой команды-дерева может не быть собственного node: права заданы у листьев.

Синтаксис взят из getUsage; ключи локализации разрешены из установленных en_us.lang.
Оставшийся ключ означает отсутствие строки в доступных ресурсах. Алиасы корня
включают фактические ключи реестра. Встроенные в execute подкоманды, не оформленные
как Forge CommandTree, отражены синтаксисом корня и не считаются отдельными записями.
Клиентские команды/клавиши и пункты GUI не принадлежат серверному реестру.

## WayofTime.bloodmagic.command

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /bloodmagic | — | 2 | — | /bloodmagic help |

## WayofTime.bloodmagic.command.sub

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /bloodmagic bind | — | 2 | — | /bloodmagic bind [true\|false] [player] (&quot;?&quot; or &quot;help&quot; for help) |
| /bloodmagic network | — | 2 | — | /bloodmagic network [syphon\|add\|get\|fill\|cap] player [amount] |
| /bloodmagic network add | — | 2 | — | /bloodmagic network add [player] [amount] |
| /bloodmagic network cap | — | 2 | — | /bloodmagic network cap [player] |
| /bloodmagic network fill | — | 2 | — | /bloodmagic network fill [player] |
| /bloodmagic network get | — | 2 | — | /bloodmagic network get [player] |
| /bloodmagic network set | — | 2 | — | /bloodmagic network set [player] [amount] |
| /bloodmagic network syphon | — | 2 | — | /bloodmagic network syphon [player] [amount] |
| /bloodmagic network tickethistory | — | 2 | — | /bloodmagic network tickethistory [player] |
| /bloodmagic orb | — | 2 | — | /bloodmagic orb [set\|get] player [tier] (&quot;?&quot; or &quot;help&quot; for help) |
| /bloodmagic orb get | — | 4 | — | /bloodmagic orb get [player\|?\|help] |
| /bloodmagic orb set | — | 4 | — | /bloodmagic orb set [player\|?\|help] |
| /bloodmagic ritual | — | 2 | — |  |
| /bloodmagic ritual create | — | 4 | — | Creates the specified ritual with the MRS at your feet, ignores other blocks by default. (Optional parameters: ([&lt;player&gt; (safe\|true\|false)] \| [safe\|true\|false])) |
| /bloodmagic ritual repair | — | 4 | — | commands.bloodmagic.ritual.repair.usage |
| /bloodmagic teleposer | — | 2 | — | Teleposer Utilities (&quot;?&quot; or &quot;help&quot; for help) |
| /bloodmagic teleposer list | — | 2 | — | /bloodmagic teleposer list [player\|?\|help] |
| /bloodmagic teleposer remove | — | 2 | — | /bloodmagic teleposer remove [ID\|?\|help] |
| /bloodmagic teleposer removeall | — | 2 | — | /bloodmagic teleposer removeall [player\|?\|help] |
| /bloodmagic teleposer rmrf | — | 2 | — | /bloodmagic teleposer rmrf [ID\|?\|help] |
| /bloodmagic teleposer teleport | — | 2 | — | /bloodmagic teleposer teleport [ID\|?\|help] |
| /bloodmagic teleposer teleportfocus | — | 2 | — | /bloodmagic teleposer teleportfocus [ID\|?\|help] |

## abyssalcraft

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /acunlockallknowledge | — | 4 | command.abyssalcraft.acunlockallknowledge | /acunlockallknowledge |

## agricraft

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /ac.nbt | — | — | command.agricraft.ac.nbt | ac.nbt &lt;list\|get&gt; &lt;name&gt; |
| /ac.stat | — | — | command.agricraft.ac.stat | ac.stat &lt;set\|get&gt; &lt;growth\|gain\|strength\|all&gt; &lt;value&gt; |

## alchemistry

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /dissolver | — | 4 | command.alchemistry.dissolver | dissolver |

## appliedenergistics2

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /ae2 | — | 0 | command.appliedenergistics2.ae2 | Commands provided by Applied Energistics 2 - use /ae2 list for a list, and /ae2 help _____ for help with a command. |

## astralsorcery

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /astralsorcery | as | 2 | command.astralsorcery.astralsorcery | /astralsorcery &lt;action&gt; [player] [arguments...] |

## atum

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /atumweather | — | 2 | command.atum.atumweather | atum.commands.weather.usage |

## baubles

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /baubles | bau, baub | 2 | command.baubles.baubles | /baubles &lt;action&gt; [&lt;player&gt; [&lt;params&gt;]] |

## betterbuilderswands

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /wandOops | — | 0 | command.betterbuilderswands.wandOops | /wandOops |

## betternether

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /findNetherCity | — | 4 | command.betternether.findNetherCity | /findNetherCity or /findNetherCity x y z |

## betterquesting

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /bq_admin | — | 2 | command.betterquesting.bq_admin | /bq_admin edit [true\|false], /bq_admin hardcore [true\|false], /bq_admin reset [all\|&lt;quest_id&gt;] [username\|uuid], /bq_admin complete &lt;quest_id&gt; [username\|uuid], /bq_admin delete [all\|&lt;quest_id&gt;], /bq_admin default [save\|load\|set] [file_name], /bq_admin lives [add\|set\|max\|default] &lt;value&gt; [username\|uuid], /bq_admin purge_hidden_quests |
| /bq_user | — | 0 | command.betterquesting.bq_user | /bq_user help, /bq_user refresh, /bq_user hardcore |

## bewitchment

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /curse | — | 2 | command.bewitchment.curse | /curse &lt;player&gt; &lt;get/add/remove/clear&gt; &lt;time&gt; |
| /fortune | — | 2 | command.bewitchment.fortune | /fortune &lt;player&gt; &lt;get/set/remove/execute&gt; |

## biometweaker

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /BTInfo | biometweakerinfo, bti, biometweakeri, btinfo | — | command.biometweaker.BTInfo | biometweaker.msg.info.usage.text |
| /BTListBiomes | btb, biometweakerb, btbiomes, btlistbiomes, biometweakerbiomes | — | command.biometweaker.BTListBiomes | biometweaker.msg.listbiomes.usage.text |
| /BTOutput | bto, biometweakero, btoutput, biometweakeroutput | — | command.biometweaker.BTOutput | biometweaker.msg.output.usage.text |
| /BTReload | btr, btreload, biometweakerr, biometweakerreload | — | command.biometweaker.BTReload | biometweaker.msg.reload.usage.text |
| /BTReloadScript | btrs, btreloadscript, biometweakerrs, btrscript, biometweakerreloadscript | — | command.biometweaker.BTReloadScript | biometweaker.msg.reloadscript.usage.text |
| /BTSetBiome | bts, btsetbiome, biometweakers, biometweakersetbiome | — | command.biometweaker.BTSetBiome | biometweaker.msg.setbiome.usage.text |

## blusunrize.immersiveengineering.common.util.commands

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /ie | — | 4 | — | Use &quot;/ie help&quot; for more information |
| /ie clearshaders | — | 4 | command.immersiveengineering.ie.clearshaders | /ie clearshaders [player name] |
| /ie mineral | — | 4 | — | Use &quot;/ie mineral help&quot; for more information |
| /ie mineral get | — | 4 | command.immersiveengineering.ie.mineral.get | /mineral get |
| /ie mineral list | — | 4 | command.immersiveengineering.ie.mineral.list | /mineral list |
| /ie mineral set | — | 4 | command.immersiveengineering.ie.mineral.set | /mineral set &lt;mineral name&gt; (surround the name in &lt;angle brackets&gt; if it contains a space) |
| /ie mineral setDepletion | — | 4 | command.immersiveengineering.ie.mineral.setDepletion | /mineral setDepletion &lt;depletion&gt; |

## bnbgaminglib

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /bnb | — | — | command.bnbgaminglib.bnb | bnbgaminglib.cmd.item.usage |

## botania

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /botania-open | — | 0 | command.botania.botania-open | &lt;entry&gt; |
| /botania-share | — | 0 | command.botania.botania-share | &lt;entry&gt; |

## bq_standard

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /bqs_advancement_dump | — | 2 | command.bq_standard.bqs_advancement_dump | /bqs_advancement_dump |
| /bqs_loot | — | 2 | command.bq_standard.bqs_loot | /bqs_loot default [save\|load], /bqs_loot delete [all\|&lt;loot_id&gt;] |

## brandonscore

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /bcore_ticktime | — | 2 | command.brandonscore.bcore_ticktime | /bcore_ticktime |
| /bcore_util | — | 3 | command.brandonscore.bcore_util | /bcore_util help |
| /tpx | — | 2 | command.brandonscore.tpx | bc.commands.tpx.usage |

## buildinggadgets

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /DeleteBlockMaps | deleteblockmaps, buildinggadgets | 4 | command.buildinggadgets.DeleteBlockMaps | DeleteBlockMaps &lt;player&gt; |
| /FindBlockMaps | findblockmaps | 4 | command.buildinggadgets.FindBlockMaps | FindBlockMaps &lt;player&gt; |

## codechicken.enderstorage.command

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /EnderStorage | ES, es, enderstorage | 0 | — | /EnderStorage help |
| /EnderStorage clear | — | 4 | command.enderstorage.EnderStorage.clear | Provides ability to clear a users EnderStorage. |

## codechicken.lib.command.help

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /EnderStorage help | — | 0 | command.enderstorage.EnderStorage.help | Displays help for /EnderStorage commands. |

## cofh.cofhworld.command

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /cofhworld | — | -1 | — | cofhworld.usage |
| /cofhworld list | — | 1 | command.cofhworld.cofhworld.list | cofhworld.list.usage |
| /cofhworld reload | — | 4 | command.cofhworld.cofhworld.reload | cofhworld.reload.usage |
| /cofhworld version | — | -1 | command.cofhworld.cofhworld.version | cofhworld.version.usage |

## cofhcore

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /cofh | — | -1 | command.cofhcore.cofh | /cofh help |

## com.bloodnbonesgaming.triumph.commands

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /triumph | — | 0 | — | Use /triumph &lt;subcommand&gt; |
| /triumph debug | — | 3 | command.triumph.triumph.debug | Use /triumph debug |

## com.feed_the_beast.mods.ftbbackups.command

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /backup | — | 0 | — | command.backup.usage |
| /backup size | — | 2 | command.ftbbackups.backup.size | /backup size |
| /backup start | — | 2 | command.ftbbackups.backup.start | /backup start [custom name] |
| /backup time | — | 0 | command.ftbbackups.backup.time | /backup time |

## com.teamacronymcoders.base.command

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /base | — | 4 | — | /base recipes |
| /base recipes | — | 4 | — | /recipes reload |

## com.teamacronymcoders.base.recipesystem.command

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /base recipes reload | — | 4 | command.base.base.recipes.reload | Reloads the Recipe System |

## crafttweaker

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /crafttweaker | minetweaker, ct, mt | 4 | command.crafttweaker.crafttweaker | /crafttweaker biomeTypes \| biomes \| blockinfo \| blockmaterial \| blocks \| botania \| botbrews \| botlexcats \| botlexentries \| botlexpages \| botlextypes \| botorechid \| bugs \| chiselGroups \| clean \| conflict \| copy \| creativetab \| discord \| dj2addons \| docs \| dumpzs \| enchants \| entities \| foods \| gases \| give \| hand \| help \| infuseTypes \| inventory \| jeiCategories \| json \| keyNames \| liquids \| log \| loottables \| materialparts \| materials \| mekrecipes \| mods \| names \| nbt \| oredict \| parts \| parttypes \| potions \| recipeNames \| recipes \| reload \| roots_properties \| roots_recipes \| scripts \| seeds \| soundevent \| soundtype \| stats \| syntax \| thaumcraftDump \| ticmat \| wiki \| zslint |

## cyclopscore

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /commoncapabilities | — | — | command.cyclopscore.commoncapabilities | /commoncapabilities &lt;config \| version&gt; |
| /cyclopscore | cyclops | — | command.cyclopscore.cyclopscore | /cyclopscore &lt;ignite \| debug \| dumpregistries \| reloadresources \| config \| version \| recursion&gt; |
| /evilcraft | — | — | command.cyclopscore.evilcraft | /evilcraft &lt;config \| version&gt; |
| /evilcraftcompat | — | — | command.cyclopscore.evilcraftcompat | /evilcraftcompat &lt;config \| version&gt; |
| /integrateddynamics | — | — | command.cyclopscore.integrateddynamics | /integrateddynamics &lt;networkdiagnostics \| config \| version \| crash&gt; |
| /integrateddynamicscompat | — | — | command.cyclopscore.integrateddynamicscompat | /integrateddynamicscompat &lt;config \| version&gt; |
| /integratedtunnels | — | — | command.cyclopscore.integratedtunnels | /integratedtunnels &lt;config \| version&gt; |
| /integratedtunnelscompat | — | — | command.cyclopscore.integratedtunnelscompat | /integratedtunnelscompat &lt;config \| version&gt; |

## draconicevolution

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /de_reload_custom_fusion | — | 3 | command.draconicevolution.de_reload_custom_fusion | Usage: /de_reload_custom_fusion |
| /de_upgrade | — | 4 | command.draconicevolution.de_upgrade | /de_upgrade |

## endercore

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /reloadServerConfigs | — | 2 | command.endercore.reloadServerConfigs | /reloadServerConfigs &lt;modid&gt; (&lt;modid2&gt; &lt;modid3&gt; ...) |
| /scoreboardinfo | — | 0 | command.endercore.scoreboardinfo | /scoreboardinfo &lt;board&gt; &lt;name&gt; |

## enderio

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /enderio | — | 4 | command.enderio.enderio | /enderio config set &lt;section&gt; &lt;key&gt; &lt;value&gt;\|config get &lt;section&gt; &lt;key&gt;\|config list [&lt;section&gt;]\|config save\|config help |

## extrautils2

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /xudebug | — | 4 | command.extrautils2.xudebug | xudebug |

## forge

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /backup help | — | 0 | — | commands.forge.usage.help |
| /backup help size | — | 0 | command.ftbbackups.backup.help.size | /backup size |
| /backup help start | — | 0 | command.ftbbackups.backup.help.start | /backup start [custom name] |
| /backup help time | — | 0 | command.ftbbackups.backup.help.time | /backup time |
| /bloodmagic bind help | — | 0 | — | commands.forge.usage.help |
| /bloodmagic help | — | 0 | — | commands.forge.usage.help |
| /bloodmagic help bind | — | 0 | command.bloodmagic.bloodmagic.help.bind | /bloodmagic bind [true\|false] [player] (&quot;?&quot; or &quot;help&quot; for help) |
| /bloodmagic help network | — | 0 | command.bloodmagic.bloodmagic.help.network | /bloodmagic network [syphon\|add\|get\|fill\|cap] player [amount] |
| /bloodmagic help orb | — | 0 | command.bloodmagic.bloodmagic.help.orb | /bloodmagic orb [set\|get] player [tier] (&quot;?&quot; or &quot;help&quot; for help) |
| /bloodmagic help ritual | — | 0 | command.bloodmagic.bloodmagic.help.ritual |  |
| /bloodmagic help teleposer | — | 0 | command.bloodmagic.bloodmagic.help.teleposer | Teleposer Utilities (&quot;?&quot; or &quot;help&quot; for help) |
| /bloodmagic network help | — | 0 | — | commands.forge.usage.help |
| /bloodmagic network help add | — | 0 | command.bloodmagic.bloodmagic.network.help.add | /bloodmagic network add [player] [amount] |
| /bloodmagic network help cap | — | 0 | command.bloodmagic.bloodmagic.network.help.cap | /bloodmagic network cap [player] |
| /bloodmagic network help fill | — | 0 | command.bloodmagic.bloodmagic.network.help.fill | /bloodmagic network fill [player] |
| /bloodmagic network help get | — | 0 | command.bloodmagic.bloodmagic.network.help.get | /bloodmagic network get [player] |
| /bloodmagic network help set | — | 0 | command.bloodmagic.bloodmagic.network.help.set | /bloodmagic network set [player] [amount] |
| /bloodmagic network help syphon | — | 0 | command.bloodmagic.bloodmagic.network.help.syphon | /bloodmagic network syphon [player] [amount] |
| /bloodmagic network help tickethistory | — | 0 | command.bloodmagic.bloodmagic.network.help.tickethistory | /bloodmagic network tickethistory [player] |
| /bloodmagic orb help | — | 0 | — | commands.forge.usage.help |
| /bloodmagic orb help get | — | 0 | command.bloodmagic.bloodmagic.orb.help.get | /bloodmagic orb get [player\|?\|help] |
| /bloodmagic orb help set | — | 0 | command.bloodmagic.bloodmagic.orb.help.set | /bloodmagic orb set [player\|?\|help] |
| /bloodmagic ritual help | — | 0 | — | commands.forge.usage.help |
| /bloodmagic ritual help create | — | 0 | command.bloodmagic.bloodmagic.ritual.help.create | Creates the specified ritual with the MRS at your feet, ignores other blocks by default. (Optional parameters: ([&lt;player&gt; (safe\|true\|false)] \| [safe\|true\|false])) |
| /bloodmagic ritual help repair | — | 0 | command.bloodmagic.bloodmagic.ritual.help.repair | commands.bloodmagic.ritual.repair.usage |
| /bloodmagic teleposer help | — | 0 | — | commands.forge.usage.help |
| /bloodmagic teleposer help list | — | 0 | command.bloodmagic.bloodmagic.teleposer.help.list | /bloodmagic teleposer list [player\|?\|help] |
| /bloodmagic teleposer help remove | — | 0 | command.bloodmagic.bloodmagic.teleposer.help.remove | /bloodmagic teleposer remove [ID\|?\|help] |
| /bloodmagic teleposer help removeall | — | 0 | command.bloodmagic.bloodmagic.teleposer.help.removeall | /bloodmagic teleposer removeall [player\|?\|help] |
| /bloodmagic teleposer help rmrf | — | 0 | command.bloodmagic.bloodmagic.teleposer.help.rmrf | /bloodmagic teleposer rmrf [ID\|?\|help] |
| /bloodmagic teleposer help teleport | — | 0 | command.bloodmagic.bloodmagic.teleposer.help.teleport | /bloodmagic teleposer teleport [ID\|?\|help] |
| /bloodmagic teleposer help teleportfocus | — | 0 | command.bloodmagic.bloodmagic.teleposer.help.teleportfocus | /bloodmagic teleposer teleportfocus [ID\|?\|help] |
| /forge | — | 0 | — | commands.forge.usage |
| /forge dimensions | — | 0 | command.forge.dimensions | commands.forge.dimensions.usage |
| /forge entity | — | 2 | — | commands.forge.entity.usage |
| /forge entity help | — | 0 | — | commands.forge.usage.help |
| /forge entity help list | — | 0 | command.forge.entity.help.list | commands.forge.entity.list.usage |
| /forge entity list | — | 2 | command.forge.entity.list | commands.forge.entity.list.usage |
| /forge generate | gen | 4 | command.forge.generate | commands.forge.gen.usage |
| /forge help | — | 0 | — | commands.forge.usage.help |
| /forge help dimensions | — | 0 | command.forge.help.dimensions | commands.forge.dimensions.usage |
| /forge help entity | — | 0 | command.forge.help.entity | commands.forge.entity.usage |
| /forge help generate | — | 0 | command.forge.help.generate | commands.forge.gen.usage |
| /forge help setdimension | — | 0 | command.forge.help.setdimension | commands.forge.setdim.usage |
| /forge help tps | — | 0 | command.forge.help.tps | commands.forge.tps.usage |
| /forge help track | — | 0 | command.forge.help.track | commands.forge.tracking.usage |
| /forge setdimension | setdim | 2 | command.forge.setdimension | commands.forge.setdim.usage |
| /forge tps | — | 0 | command.forge.tps | commands.forge.tps.usage |
| /forge track | — | 2 | — | commands.forge.tracking.usage |
| /forge track entity | — | 4 | command.forge.track.entity | commands.forge.tracking.entity.usage |
| /forge track help | — | 0 | — | commands.forge.usage.help |
| /forge track help entity | — | 0 | command.forge.track.help.entity | commands.forge.tracking.entity.usage |
| /forge track help reset | — | 0 | command.forge.track.help.reset | commands.forge.tracking.reset.usage |
| /forge track help start | — | 0 | command.forge.track.help.start | commands.forge.tracking.start.usage |
| /forge track help te | — | 0 | command.forge.track.help.te | commands.forge.tracking.te.usage |
| /forge track reset | — | 2 | command.forge.track.reset | commands.forge.tracking.reset.usage |
| /forge track start | — | 2 | command.forge.track.start | commands.forge.tracking.start.usage |
| /forge track te | — | 4 | command.forge.track.te | commands.forge.tracking.te.usage |
| /ie help | — | 0 | — | commands.forge.usage.help |
| /ie help clearshaders | — | 0 | command.immersiveengineering.ie.help.clearshaders | /ie clearshaders [player name] |
| /ie help mineral | — | 0 | command.immersiveengineering.ie.help.mineral | Use &quot;/ie mineral help&quot; for more information |
| /ie mineral help | — | 0 | — | commands.forge.usage.help |
| /ie mineral help get | — | 0 | command.immersiveengineering.ie.mineral.help.get | /mineral get |
| /ie mineral help list | — | 0 | command.immersiveengineering.ie.mineral.help.list | /mineral list |
| /ie mineral help set | — | 0 | command.immersiveengineering.ie.mineral.help.set | /mineral set &lt;mineral name&gt; (surround the name in &lt;angle brackets&gt; if it contains a space) |
| /ie mineral help setDepletion | — | 0 | command.immersiveengineering.ie.mineral.help.setDepletion | /mineral setDepletion &lt;depletion&gt; |

## ftblib

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /my_settings | — | 0 | command.ftblib.my_settings | /my_settings &lt;config id&gt; [value] |
| /reload | — | 2 | command.ftblib.reload | /reload [*\|domain:*\|domain:id] |
| /team | — | 0 | — | /team |
| /team create | — | 0 | command.ftblib.team.create | /team create &lt;id&gt; [color] |
| /team create_server_team | — | 2 | command.ftblib.team.create_server_team | /team create_server_team &lt;id&gt; |
| /team delete | — | 2 | command.ftblib.team.delete | /team delete &lt;team&gt; |
| /team get | — | 0 | command.ftblib.team.get | /team get &lt;player&gt; |
| /team help | ? | 0 | command.ftblib.team.help | /help [page\|command name] |
| /team info | — | 0 | command.ftblib.team.info | /team info &lt;team&gt; |
| /team join | — | 0 | command.ftblib.team.join | /team join &lt;team&gt; |
| /team kick | — | 0 | command.ftblib.team.kick | /team kick &lt;player&gt; |
| /team leave | — | 0 | command.ftblib.team.leave | /team leave |
| /team list | — | 0 | command.ftblib.team.list | /team list |
| /team request_invite | — | 0 | command.ftblib.team.request_invite | /team request_invite &lt;team&gt; |
| /team settings | — | 0 | command.ftblib.team.settings | /team settings &lt;config id&gt; [value] |
| /team settings_for | — | 2 | command.ftblib.team.settings_for | commands.team.settings_for.usage |
| /team status | set_status | 0 | command.ftblib.team.status | /team status &lt;player&gt; [set_status] |
| /team transfer_ownership | — | 0 | command.ftblib.team.transfer_ownership | /team transfer_ownership &lt;player&gt; |

## ftbutilities

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /back | — | 0 | command.ftbutilities.back | /back |
| /chunks | — | 0 | — | /chunks |
| /chunks claim | — | 0 | command.ftbutilities.chunks.claim | /chunks claim |
| /chunks claim_as | — | 2 | command.ftbutilities.chunks.claim_as | /chunks claim_as &lt;server team&gt; [radius in chunks] |
| /chunks help | ? | 0 | command.ftbutilities.chunks.help | /help [page\|command name] |
| /chunks info | — | 0 | command.ftbutilities.chunks.info | /chunks info |
| /chunks load | — | 0 | command.ftbutilities.chunks.load | /chunks load |
| /chunks unclaim | — | 0 | command.ftbutilities.chunks.unclaim | /chunks unclaim |
| /chunks unclaim_all | — | 0 | command.ftbutilities.chunks.unclaim_all | /chunks unclaim_all [dimension] [player] |
| /chunks unclaim_everything | — | 2 | command.ftbutilities.chunks.unclaim_everything | /chunks unclaim_everything [dimension] |
| /chunks unload | — | 0 | command.ftbutilities.chunks.unload | /chunks unload [player] |
| /chunks unload_all | — | 0 | command.ftbutilities.chunks.unload_all | /chunks unload_all [dimension] [player] |
| /chunks unload_everything | — | 2 | command.ftbutilities.chunks.unload_everything | /chunks unload_everything [dimension] |
| /delhome | — | 0 | command.ftbutilities.delhome | /delhome [home] |
| /delwarp | — | 2 | command.ftbutilities.delwarp | /delwarp &lt;warp&gt; |
| /fly | — | 2 | command.ftbutilities.fly | /fly |
| /god | — | 2 | command.ftbutilities.god | commands.god.usage |
| /heal | — | 2 | command.ftbutilities.heal | /heal [player] |
| /home | — | 0 | command.ftbutilities.home | /home [list\|list_all\|home] [player] |
| /inv | — | 0 | — | /inv |
| /inv disable_right_click | — | 2 | command.ftbutilities.inv.disable_right_click | commands.inv.disable_right_click.usage |
| /inv help | ? | 0 | command.ftbutilities.inv.help | /help [page\|command name] |
| /inv view | edit | 2 | command.ftbutilities.inv.view | /inv view &lt;player&gt; |
| /kickme | — | 0 | command.ftbutilities.kickme | /kickme |
| /killall | — | 2 | command.ftbutilities.killall | /killall [type] [dimension] |
| /leaderboards | — | 0 | command.ftbutilities.leaderboards | /leaderboards [id] |
| /mute | — | 2 | command.ftbutilities.mute | /mute &lt;player&gt; |
| /nbtedit | — | 0 | — | /nbtedit |
| /nbtedit block | — | 2 | command.ftbutilities.nbtedit.block | /nbtedit block &lt;x&gt; &lt;y&gt; &lt;z&gt; |
| /nbtedit entity | — | 2 | command.ftbutilities.nbtedit.entity | /nbtedit entity &lt;id&gt; |
| /nbtedit help | ? | 0 | command.ftbutilities.nbtedit.help | /help [page\|command name] |
| /nbtedit item | — | 2 | command.ftbutilities.nbtedit.item | /nbtedit item |
| /nbtedit player | me | 2 | command.ftbutilities.nbtedit.player | /nbtedit player &lt;player&gt; |
| /nick | — | 0 | command.ftbutilities.nick | /nick &lt;name...&gt; |
| /nickfor | — | 2 | command.ftbutilities.nickfor | /nickfor &lt;player&gt; &lt;name...&gt; |
| /ranks | — | 0 | — | /ranks |
| /ranks add | — | 2 | command.ftbutilities.ranks.add | /ranks add &lt;rank\|player&gt; &lt;rank&gt; |
| /ranks create | — | 2 | command.ftbutilities.ranks.create | /ranks create &lt;id&gt; [parent] |
| /ranks delete | del | 2 | command.ftbutilities.ranks.delete | /ranks delete &lt;rank&gt; |
| /ranks get_permission | getp | 2 | command.ftbutilities.ranks.get_permission | /ranks get_permission &lt;rank\|player&gt; &lt;permission&gt; |
| /ranks help | ? | 0 | command.ftbutilities.ranks.help | /help [page\|command name] |
| /ranks info | — | 0 | command.ftbutilities.ranks.info | /ranks info &lt;rank\|player&gt; |
| /ranks remove | — | 2 | command.ftbutilities.ranks.remove | /ranks remove &lt;rank\|player&gt; [rank] |
| /ranks set_permission | setp | 2 | command.ftbutilities.ranks.set_permission | /ranks set_permission &lt;rank&gt; &lt;permission&gt; &lt;true\|false\|value\|none&gt; |
| /rec | — | 0 | command.ftbutilities.rec | /rec |
| /rtp | — | 0 | command.ftbutilities.rtp | commands.rtp.usage |
| /sethome | — | 0 | command.ftbutilities.sethome | /sethome [home] |
| /setwarp | — | 2 | command.ftbutilities.setwarp | /setwarp &lt;warp&gt; &lt;player&gt;\|{&lt;x&gt; &lt;y&gt; &lt;z&gt; [dim]} |
| /shutdown | — | 2 | command.ftbutilities.shutdown | /shutdown |
| /spawn | — | 0 | command.ftbutilities.spawn | /spawn |
| /tpa | — | 0 | command.ftbutilities.tpa | /tpa &lt;player&gt; |
| /tpaccept | — | 0 | command.ftbutilities.tpaccept | /tpaccept &lt;player&gt; |
| /tpl | — | 2 | command.ftbutilities.tpl | /tpl (&lt;x&gt; &lt;y&gt; &lt;z&gt;) \| ([who] &lt;player&gt;) |
| /trash_can | — | 0 | command.ftbutilities.trash_can | /trash_can |
| /unmute | — | 2 | command.ftbutilities.unmute | /unmute &lt;player&gt; |
| /warp | — | 0 | command.ftbutilities.warp | /warp &lt;warp&gt; |

## galacticraftcore

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /dimensiontp | — | 2 | command.galacticraftcore.dimensiontp | /dimensiontp [&lt;player&gt;] |
| /gcastrominer | — | 2 | command.galacticraftcore.gcastrominer | /gcastrominer [show\|reset\|set&lt;number&gt;] &lt;playername&gt; |
| /gcenergyunits | — | 0 | command.galacticraftcore.gcenergyunits | /gcenergyunits [gJ\|J\|RF] |
| /gchelp | — | 0 | command.galacticraftcore.gchelp | /gchelp |
| /gchouston | — | 0 | command.galacticraftcore.gchouston | /gchouston [&lt;player&gt;] |
| /gcinv | — | 2 | command.galacticraftcore.gcinv | /gcinv [save\|restore\|drop\|clear] &lt;playername&gt; |
| /gckeeploaded | — | 4 | command.galacticraftcore.gckeeploaded | /gckeeploaded &lt;dimension id&gt; |
| /gckit | — | 2 | command.galacticraftcore.gckit | /gckit [&lt;player&gt;] |
| /joinrace | — | 0 | command.galacticraftcore.joinrace | /joinrace |
| /ssinvite | — | 0 | command.galacticraftcore.ssinvite | /ssinvite [ &lt;player&gt; \| +all \| -all ] |
| /ssnewowner | — | 2 | command.galacticraftcore.ssnewowner | /ssnewowner &lt;dim#&gt; &lt;player&gt; |
| /ssuninvite | — | 0 | command.galacticraftcore.ssuninvite | /ssuninvite &lt;player&gt; |

## hammercore

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /hc_buildstr | — | — | command.hammercore.hc_buildstr | Use /hc_buildstr &lt;structure, use TAB&gt; OR /hc_buildstr &lt;x&gt; &lt;y&gt; &lt;z&gt; &lt;structure, use TAB&gt; |
| /hc_export | — | 4 | command.hammercore.hc_export | /hc_export &lt;x1&gt; &lt;y1&gt; &lt;z1&gt; &lt;x2&gt; &lt;y2&gt; &lt;z2&gt; &lt;name&gt; [save air] |
| /hc_loadchunk | — | 4 | command.hammercore.hc_loadchunk | Use /hc_loadchunk &lt;dim:int&gt; &lt;chunk x:int&gt; &lt;chunk z:int&gt; &lt;time:string(or -1t for unlimited time)&gt; |
| /hc_lying_item | — | 4 | command.hammercore.hc_lying_item |  |
| /hc_postolong | — | 4 | command.hammercore.hc_postolong |  |
| /hc_reload_tick_rates | — | 4 | command.hammercore.hc_reload_tick_rates | Used to reload tick rates configs in HammerCore |
| /hc_setenchcol | — | 0 | command.hammercore.hc_setenchcol | Use /hc_setenchcol &lt;hex color&gt; to apply custom color to held item |
| /hc_setloottable | — | 4 | command.hammercore.hc_setloottable | Applies a loot table to inventory |
| /hc_timetoticks | — | 4 | command.hammercore.hc_timetoticks | Use /hc_timetoticks &lt;time:string&gt; (time example: 1t1s1m1h1d1M1y - 1 tick and 1 second and 1 minute and 1 hour and 1 day and 1 month and 1 year) |
| /hc_tpx | — | 4 | command.hammercore.hc_tpx | Used to tp between 2 points on server. Can be used between dimensions |

## journeymap

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /jtp | — | 4 | command.journeymap.jtp | /jtp &lt;x y z dim&gt; |

## laggoggles

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /laggoggles | — | 4 | command.laggoggles.laggoggles | /laggoggles |

## mekanism

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /mtp | — | 4 | command.mekanism.mtp | cmd.mek.tp.usage |
| /mtpop | — | 4 | command.mekanism.mtpop | cmd.mek.tpop.usage |

## mekanism.common.command

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /mek | — | 4 | — | cmd.mek.usage |
| /mek chunk | — | 4 | — | cmd.mek.chunk.usage |
| /mek chunk clear | — | 4 | command.mekanism.mek.chunk.clear | cmd.mek.chunk.clear.usage |
| /mek chunk flush | — | 4 | command.mekanism.mek.chunk.flush | cmd.mek.chunk.flush.usage |
| /mek chunk unwatch | — | 4 | command.mekanism.mek.chunk.unwatch | cmd.mek.chunk.unwatch.usage |
| /mek chunk watch | — | 4 | command.mekanism.mek.chunk.watch | cmd.mek.chunk.watch.usage |
| /mek debug | — | 4 | command.mekanism.mek.debug | cmd.mek.debug.usage |
| /mek testrules | — | 4 | command.mekanism.mek.testrules | cmd.mek.testrules.usage |
| /mek tp | — | 4 | command.mekanism.mek.tp | cmd.mek.tp.usage |
| /mek tpop | — | 4 | command.mekanism.mek.tpop | cmd.mek.tpop.usage |

## minecraft

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /advancement | — | 2 | command.advancement | /advancement &lt;grant\|revoke\|test&gt; &lt;player&gt; |
| /ban | — | 3 | command.ban | /ban &lt;name&gt; [reason ...] |
| /ban-ip | — | 3 | command.ban-ip | /ban-ip &lt;address\|name&gt; [reason ...] |
| /banlist | — | 3 | command.banlist | /banlist [ips\|players] |
| /blockdata | — | 2 | command.blockdata | /blockdata &lt;x&gt; &lt;y&gt; &lt;z&gt; &lt;dataTag&gt; |
| /clear | — | 2 | command.clear | /clear [player] [item] [data] [maxCount] [dataTag] |
| /clone | — | 2 | command.clone | /clone &lt;x1&gt; &lt;y1&gt; &lt;z1&gt; &lt;x2&gt; &lt;y2&gt; &lt;z2&gt; &lt;x&gt; &lt;y&gt; &lt;z&gt; [maskMode] [cloneMode] |
| /debug | — | 3 | command.debug | /debug &lt;start\|stop&gt; |
| /defaultgamemode | — | 2 | command.defaultgamemode | /defaultgamemode &lt;mode&gt; |
| /deop | — | 3 | command.deop | /deop &lt;player&gt; |
| /difficulty | — | 2 | command.difficulty | /difficulty &lt;new difficulty&gt; |
| /effect | — | 2 | command.effect | /effect &lt;player&gt; &lt;effect&gt; [seconds] [amplifier] [hideParticles] OR /effect &lt;player&gt; clear |
| /enchant | — | 2 | command.enchant | /enchant &lt;player&gt; &lt;enchantment ID&gt; [level] |
| /entitydata | — | 2 | command.entitydata | /entitydata &lt;entity&gt; &lt;dataTag&gt; |
| /execute | — | 2 | command.execute | /execute &lt;entity&gt; &lt;x&gt; &lt;y&gt; &lt;z&gt; &lt;command&gt; OR /execute &lt;entity&gt; &lt;x&gt; &lt;y&gt; &lt;z&gt; detect &lt;x&gt; &lt;y&gt; &lt;z&gt; &lt;block&gt; &lt;dataValue\|-1\|state\|*&gt; &lt;command&gt; |
| /fill | — | 2 | command.fill | /fill &lt;x1&gt; &lt;y1&gt; &lt;z1&gt; &lt;x2&gt; &lt;y2&gt; &lt;z2&gt; &lt;block&gt; [dataValue\|state] [oldBlockHandling] [dataTag] |
| /function | — | 2 | command.function | /function &lt;name&gt; [if &lt;selector&gt;\|unless &lt;selector&gt;] |
| /gamemode | — | 2 | command.gamemode | /gamemode &lt;mode&gt; [player] |
| /gamerule | — | 2 | command.gamerule | /gamerule &lt;rule name&gt; [value] |
| /give | — | 2 | command.give | /give &lt;player&gt; &lt;item&gt; [amount] [data] [dataTag] |
| /kick | — | 3 | command.kick | /kick &lt;player&gt; [reason ...] |
| /kill | — | 2 | command.kill | /kill [player\|entity] |
| /list | — | 0 | command.list | /list |
| /locate | — | 2 | command.locate | /locate &lt;feature&gt; |
| /me | — | 0 | command.me | /me &lt;action ...&gt; |
| /op | — | 3 | command.op | /op &lt;player&gt; |
| /pardon | — | 3 | command.pardon | /pardon &lt;name&gt; |
| /pardon-ip | — | 3 | command.pardon-ip | /pardon-ip &lt;address&gt; |
| /particle | — | 2 | command.particle | /particle &lt;name&gt; &lt;x&gt; &lt;y&gt; &lt;z&gt; &lt;xd&gt; &lt;yd&gt; &lt;zd&gt; &lt;speed&gt; [count] [mode] [player] [params] |
| /playsound | — | 2 | command.playsound | /playsound &lt;sound&gt; &lt;source&gt; &lt;player&gt; [x] [y] [z] [volume] [pitch] [minimumVolume] |
| /recipe | — | 2 | command.recipe | /recipe &lt;give\|take&gt; [player] &lt;name\|*&gt; |
| /replaceitem | — | 2 | command.replaceitem | /replaceitem &lt;entity\|block&gt; ... |
| /save-all | — | 4 | command.save-all | /save-all [flush] |
| /save-off | — | 4 | command.save-off | /save-off |
| /save-on | — | 4 | command.save-on | /save-on |
| /say | — | 1 | command.say | /say &lt;message ...&gt; |
| /scoreboard | — | 2 | command.scoreboard | /scoreboard &lt;objectives\|players\|teams&gt; ... |
| /seed | — | 2 | command.seed | /seed |
| /setblock | — | 2 | command.setblock | /setblock &lt;x&gt; &lt;y&gt; &lt;z&gt; &lt;block&gt; [dataValue\|state] [oldBlockHandling] [dataTag] |
| /setidletimeout | — | 3 | command.setidletimeout | /setidletimeout &lt;minutes&gt; |
| /setworldspawn | — | 2 | command.setworldspawn | /setworldspawn [&lt;x&gt; &lt;y&gt; &lt;z&gt;] |
| /spawnpoint | — | 2 | command.spawnpoint | /spawnpoint [player] [&lt;x&gt; &lt;y&gt; &lt;z&gt;] |
| /spreadplayers | — | 2 | command.spreadplayers | /spreadplayers &lt;x&gt; &lt;z&gt; &lt;spreadDistance&gt; &lt;maxRange&gt; &lt;respectTeams true\|false&gt; &lt;player ...&gt; |
| /stats | — | 2 | command.stats | /stats &lt;entity\|block&gt; ... |
| /stop | — | 4 | command.stop | /stop |
| /stopsound | — | 2 | command.stopsound | /stopsound &lt;player&gt; [source] [sound] |
| /summon | — | 2 | command.summon | /summon &lt;entityname&gt; [x] [y] [z] [dataTag] |
| /teleport | — | 2 | command.teleport | /teleport &lt;entity&gt; &lt;x&gt; &lt;y&gt; &lt;z&gt; [&lt;y-rot&gt; &lt;x-rot&gt;] |
| /tell | w, msg | 0 | command.tell | /tell &lt;player&gt; &lt;private message ...&gt; |
| /tellraw | — | 2 | command.tellraw | /tellraw &lt;player&gt; &lt;raw json message&gt; |
| /testfor | — | 2 | command.testfor | /testfor &lt;player&gt; [dataTag] |
| /testforblock | — | 2 | command.testforblock | /testforblock &lt;x&gt; &lt;y&gt; &lt;z&gt; &lt;block&gt; [dataValue\|-1\|state\|*] [dataTag] |
| /testforblocks | — | 2 | command.testforblocks | /testforblocks &lt;x1&gt; &lt;y1&gt; &lt;z1&gt; &lt;x2&gt; &lt;y2&gt; &lt;z2&gt; &lt;x&gt; &lt;y&gt; &lt;z&gt; [mode] |
| /time | — | 2 | command.time | /time &lt;set\|add\|query&gt; &lt;value&gt; |
| /title | — | 2 | command.title | /title &lt;player&gt; title\|subtitle\|actionbar\|clear\|reset\|times ... |
| /toggledownfall | — | 2 | command.toggledownfall | /toggledownfall |
| /tp | — | 2 | command.tp | /tp [target player] &lt;destination player&gt; OR /tp [target player] &lt;x&gt; &lt;y&gt; &lt;z&gt; [&lt;yaw&gt; &lt;pitch&gt;] |
| /trigger | — | 0 | command.trigger | /trigger &lt;objective&gt; &lt;add\|set&gt; &lt;value&gt; |
| /weather | — | 2 | command.weather | /weather &lt;clear\|rain\|thunder&gt; [duration in seconds] |
| /whitelist | — | 3 | command.whitelist | /whitelist &lt;on\|off\|list\|add\|remove\|reload&gt; |
| /worldborder | — | 2 | command.worldborder | /worldborder &lt;set\|center\|damage\|warning\|get\|add&gt; ... |
| /xp | — | 2 | command.xp | /xp &lt;amount&gt; [player] OR /xp &lt;amount&gt;L [player] |

## modularmachinery

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /mm-hand | — | 2 | command.modularmachinery.mm-hand | /mm-hand |
| /mm-syntax | — | 2 | command.modularmachinery.mm-syntax | /mm-syntax |

## morpheus

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /morpheus | sleepvote | 4 | command.morpheus.morpheus | /morpheus &lt;alert : version&gt; \| /morpheus percent &lt;percentage&gt; \| /morpheus disable &lt;dimension number&gt; |

## moze_intel.projecte.network.commands

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /projecte | — | 0 | — | pe.command.main.usage |
| /projecte clearKnowledge | — | 4 | command.projecte.projecte.clearKnowledge | pe.command.clearknowledge.usage |
| /projecte reloadEMC | — | 4 | command.projecte.projecte.reloadEMC | /projecte reloadEMC |
| /projecte removeEMC | — | 4 | command.projecte.projecte.removeEMC | pe.command.remove.usage |
| /projecte resetEMC | — | 4 | command.projecte.projecte.resetEMC | pe.command.reset.usage |
| /projecte setEMC | — | 4 | command.projecte.projecte.setEMC | pe.command.set.usage |
| /projecte showBag | — | 4 | command.projecte.projecte.showBag | pe.command.showbag.usage |

## mputils

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /mpadmin | mpa | 2 | command.mputils.mpadmin | &lt;/mpadmin, /mpa&gt; |

## openblocks

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /flimflam | — | — | command.openblocks.flimflam | flimflam &lt;player&gt; [&lt;effect&gt;] |
| /luck | — | — | command.openblocks.luck | luck &lt;player&gt; [&lt;amount&gt;] |
| /ob_inventory | — | — | command.openblocks.ob_inventory | ob_inventory store &lt;player&gt; OR ob_inventory restore &lt;player&gt; &lt;file without &#x27;inventory-&#x27; and &#x27;.dat&#x27;&gt; OR ob_inventory spawn &lt;file without &#x27;inventory-&#x27; and &#x27;.dat&#x27;&gt; [&lt;sub_inventory OR &#x27;main&#x27;&gt;,  [&lt;index of item&gt;]] |

## openmods

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /om_config_s | — | — | command.openmods.om_config_s | om_config_s save &lt;modid&gt; OR om_config_s help &lt;modid&gt; &lt;category&gt; &lt;name&gt; OR om_config_s get &lt;modid&gt; &lt;category&gt; &lt;name&gt; OR om_config_s clear &lt;modid&gt; &lt;category&gt; &lt;name&gt; OR om_config_s set &lt;modid&gt; &lt;category&gt; &lt;name&gt; &lt;value&gt;... OR om_config_s append &lt;modid&gt; &lt;category&gt; &lt;name&gt; &lt;value&gt;... OR om_config_s remove &lt;modid&gt; &lt;category&gt; &lt;name&gt; &lt;value&gt;... OR om_config_s default &lt;modid&gt; &lt;category&gt; &lt;name&gt; &lt;value&gt;... OR  |
| /om_source_s | — | — | command.openmods.om_source_s | om_source_s class &lt;class name&gt; |

## oreexcavation

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /undo_excavation | — | 0 | command.oreexcavation.undo_excavation | /undo_excavation |
| /undo_excavation_forced | — | 4 | command.oreexcavation.undo_excavation_forced | /undo_excavation_forced &lt;player&gt; |

## planetprogression

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /addNewSatellite | — | 3 | command.planetprogression.addNewSatellite | /addNewSatellite &lt;player&gt; |
| /removeAllSatellites | — | 3 | command.planetprogression.removeAllSatellites | /removeAllSatellites &lt;player&gt; |
| /removeAllUnlockedCelestialBody | — | 3 | command.planetprogression.removeAllUnlockedCelestialBody | /removeAllUnlockedCelestialBody &lt;player&gt; |
| /removeUnlockedCelestialBody | — | 3 | command.planetprogression.removeUnlockedCelestialBody | /removeUnlockedCelestialBody &lt;player&gt; &lt;celestialBodyName&gt; |
| /unlockAllCelestialBodies | — | 3 | command.planetprogression.unlockAllCelestialBodies | /unlockAllCelestialBodies &lt;player&gt; |
| /unlockCelestialBody | — | 3 | command.planetprogression.unlockCelestialBody | /unlockCelestialBody &lt;player&gt; &lt;celestialBodyName&gt; |

## quark

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /quark-config | quarkconfig | 2 | command.quark.quark-config | /quark-config &lt;category&gt; &lt;key&gt; &lt;value&gt; [player] [save?] |

## reborncore

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /rc_dumpmods | — | 4 | command.reborncore.rc_dumpmods | rc_dumpmods |
| /rc_listRecipes | — | 4 | command.reborncore.rc_listRecipes | rc_listRecipes |

## reccomplex

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /#&amp; | — | 4 | command.reccomplex.#&amp; | #&amp;  &lt;1&gt;... |
| /#as | — | 4 | command.reccomplex.#as | #as  &lt;commands.parameters.entity&gt; &lt;commands.parameters.command&gt; [args...]... |
| /#biome | — | 2 | command.reccomplex.#biome | #biome &lt;help\|search\|types\|list&gt; |
| /#cancel | — | 2 | command.reccomplex.#cancel | #cancel  |
| /#confirm | — | 2 | command.reccomplex.#confirm | #confirm  |
| /#copy | — | 2 | command.reccomplex.#copy | #copy  |
| /#decorate | — | 2 | command.reccomplex.#decorate | #decorate  [z1] [x1] [z2] [x2] --one --exp [null] |
| /#delete | — | 4 | command.reccomplex.#delete | #delete  &lt;file type&gt; [resource expression]... --directory &lt;directory&gt; |
| /#dimension | — | 2 | command.reccomplex.#dimension | #dimension &lt;help\|types\|list&gt; |
| /#edit | — | 4 | command.reccomplex.#edit | #edit  [structure] --from [structure] --id [export id] --directory [directory] |
| /#eval | — | 2 | command.reccomplex.#eval | #eval  [dependency expression] |
| /#export | — | 4 | command.reccomplex.#export | #export  [copy structure] --id [export id] --directory [directory] |
| /#fill | — | 2 | command.reccomplex.#fill | #fill  [commands.parameters.block] [source expression]... --metadata [metadata] --shape [shape] --flood [direction expression] |
| /#gen | — | 2 | command.reccomplex.#gen | #gen  &lt;structure&gt; --mirror --select --seed [seed] --rotation [commands.parameters.rotation] --suggest --gen [generation type id] -x [commands.parameters.x] -z [commands.parameters.z] --dimension [commands.parameters.dimension] |
| /#import | — | 2 | command.reccomplex.#import | #import  [structure] --mirror --select --rotation [commands.parameters.rotation] -x [commands.parameters.x] -y [commands.parameters.y] -z [commands.parameters.z] --dimension [commands.parameters.dimension] |
| /#map | — | 4 | command.reccomplex.#map | #map  &lt;resource expression\|structure&gt; [virtual command] [args...]... --nosave --directory [directory] |
| /#move | — | 2 | command.reccomplex.#move | #move  --mirror --rotation [commands.parameters.rotation] --noselect --duplicate --times [1] -x [commands.parameters.x] -y [commands.parameters.y] -z [commands.parameters.z] |
| /#natural | — | 0 | command.reccomplex.#natural | #natural &lt;help\|floor\|smart\|space&gt; |
| /#paste | — | 2 | command.reccomplex.#paste | #paste  --mirror --select --seed [null] --rotation [commands.parameters.rotation] -x [commands.parameters.x] -y [commands.parameters.y] -z [commands.parameters.z] --generate |
| /#preview | — | 2 | command.reccomplex.#preview | #preview  &lt;type&gt; |
| /#property | — | 2 | command.reccomplex.#property | #property  &lt;key&gt; &lt;value&gt; --shape [shape] --exp [positioned block expression] |
| /#reload | — | 4 | command.reccomplex.#reload | #reload  [level] |
| /#reopen | — | 2 | command.reccomplex.#reopen | #reopen  |
| /#retro | — | 2 | command.reccomplex.#retro | #retro  --exp [resource expression: only generate these structures] --dimension [commands.parameters.dimension] |
| /#sanity | — | 2 | command.reccomplex.#sanity | #sanity  --silent --short |
| /#schematic | — | 0 | command.reccomplex.#schematic | #schematic &lt;help\|import\|convert\|export&gt; |
| /#selection | — | 2 | command.reccomplex.#selection | #selection &lt;help\|expand\|set\|shrink\|get\|wand\|clear\|crop&gt; |
| /#setbiome | — | 2 | command.reccomplex.#setbiome | #setbiome  [commands.parameters.biome] |
| /#sight | — | 0 | command.reccomplex.#sight | #sight &lt;remember\|help\|forget\|check\|info&gt; |
| /#structures | — | 0 | command.reccomplex.#structures | #structures &lt;help\|lookup\|search\|tweak\|list&gt; |
| /#vanilla | — | 0 | command.reccomplex.#vanilla | #vanilla &lt;help\|gen\|check&gt; |
| /#visual | — | 2 | command.reccomplex.#visual | #visual  &lt;type&gt; &lt;true\|false&gt; |
| /#whatisthis | — | 2 | command.reccomplex.#whatisthis | #whatisthis  [commands.parameters.x] [commands.parameters.y] [commands.parameters.z] |
| /#write | — | 4 | command.reccomplex.#write | #write  &lt;file type&gt; [resource expression]... --directory [directory] |

## rftools

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /rftcfg | — | — | command.rftools.rftcfg | rftcfg &lt;subcommand&gt; &lt;args&gt; (try &#x27;rftcfg help&#x27; for more info) |
| /rftshape | — | — | command.rftools.rftshape | rftshape &lt;subcommand&gt; &lt;args&gt; (try &#x27;rftshape help&#x27; for more info) |
| /rfttp | — | — | command.rftools.rfttp | rfttp &lt;subcommand&gt; &lt;args&gt; (try &#x27;rfttp help&#x27; for more info) |

## rftoolsdim

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /rftdb | — | — | command.rftoolsdim.rftdb | rftdb &lt;subcommand&gt; &lt;args&gt; (try &#x27;rftdb help&#x27; for more info) |
| /rftdim | — | — | command.rftoolsdim.rftdim | rftdim &lt;subcommand&gt; &lt;args&gt; (try &#x27;rftdim help&#x27; for more info) |

## roots

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /ritual | — | 2 | command.roots.ritual | /ritual &lt;ritual name&gt; |
| /roots | — | 2 | command.roots.roots | /roots book \| /roots activate \| /roots rituals \| /roots growables \| /roots spells \| /roots library \| /roots modifiers \| /roots slave |
| /staff | — | 2 | command.roots.staff | /staff &lt;spell name&gt; |

## ruins

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /parseruin | — | 2 | command.ruins.parseruin | /parseruin TEMPLATENAME sets the Ruins World2Template parser to wait for the next block you break, which will be considered part of the template baseplate |
| /testruin | — | 2 | command.ruins.testruin | /testruin TEMPLATENAME [X Y Z [ROTATION [IGNORE_CEILING]]] manually spawns the target Ruin of the templateparser folder, [] optional |
| /undoruin | — | 2 | command.ruins.undoruin | /undoruin restores the site of the last testruin command |

## spark

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /spark | — | — | command.spark.spark | /spark |

## storagedrawers

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /storagedrawers | — | 4 | command.storagedrawers.storagedrawers | commands.storagedrawers.usage |

## thaumcraft

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /thaumcraft | tc, thaum | 2 | command.thaumcraft.thaumcraft | /thaumcraft &lt;action&gt; [&lt;player&gt; [&lt;params&gt;]] |

## thaumicaugmentation

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /thaumicaugmentation | ta | — | command.thaumicaugmentation.thaumicaugmentation | thaumicaugmentation &lt;fixaura\|ward\|makefracture\|&gt; |

## tk.zeitheron.solarflux.command

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /solarflux | sf, sfr | 4 | — | /solarflux &lt;sub&gt; |
| /solarflux reload | — | 4 | command.solarflux.solarflux.reload | /solarflux reload |

## tombmanygraves

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /tmg_drop | — | — | command.tombmanygraves.tmg_drop | tmg_drop &lt;player&gt; &lt;timestamp or latest&gt; [receiving player] |
| /tmg_friends | — | — | command.tombmanygraves.tmg_friends | tmg_friends [add/remove/list] [player] |
| /tmg_getDeathList | tmg_deathlist | — | command.tombmanygraves.tmg_getDeathList | tmg_getDeathList [player] &lt;timestamp or latest&gt; |
| /tmg_pop_grave | — | — | command.tombmanygraves.tmg_pop_grave | tmg_pop_grave [x] [y] [z] |
| /tmg_restore | — | — | command.tombmanygraves.tmg_restore | tmg_restore &lt;player&gt; &lt;timestamp or latest&gt; [receiving player] |
| /tmg_steal | — | — | command.tombmanygraves.tmg_steal | tmg_steal [x] [y] [z] |
| /tmg_toggle_grave_pos | — | — | command.tombmanygraves.tmg_toggle_grave_pos | tmg_toggle_grave_pos |
| /tmg_toggle_render | — | — | command.tombmanygraves.tmg_toggle_render | tmg_toggle_render |

## toolprogression

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /tpr | toolprogression | 4 | command.toolprogression.tpr | tpr reload \| set &lt;toolclass&gt; &lt;level&gt; [&lt;hardness&gt;] \| unset \| get |

## torchmaster

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /torchmaster_entity_dump | — | 4 | command.torchmaster.torchmaster_entity_dump | /torchmaster_entity_dump |
| /torchmaster_torch_list | — | 4 | command.torchmaster.torchmaster_torch_list | /torchmaster_torch_list |

## traverse

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /findbiome | — | 4 | command.traverse.findbiome | /findbiome &lt;biome&gt; |

## twilightforest

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /tffeature | tf, twilightforest | 2 | command.twilightforest.tffeature | /tffeature &lt;info\|reactivate\|conquer\|center&gt; |

## universaltweaks

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /help | ? | 0 | command.universaltweaks.help | /help [page\|command name] |

## valkyrielib

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /removeowner | — | 3 | command.valkyrielib.removeowner | valkyrielib.removeowner |

## waila

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /dumphandlers | — | 3 | command.waila.dumphandlers | /dumphandlers |

## wrcbe

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /freq | — | — | command.wrcbe.freq | /freq help |

## youyihj.zenutils.api.command

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /dj2 | — | 0 | — | Command Usage is undefined. |
| /dj2 book_of_logic | — | 0 | command.zenutils.book_of_logic | commands.book_of_logic.usage |
| /dj2 bugs | — | 0 | command.zenutils.dj2.bugs | commands.issues.usage |
| /dj2 curseforge | — | 0 | command.zenutils.curseforge | commands.curseforge.usage |
| /dj2 discord | — | 0 | command.zenutils.discord | commands.discord.usage |
| /dj2 introduction_book | — | 0 | command.zenutils.introduction_book | commands.introduction_book.usage |
| /dj2 issues | — | 0 | command.zenutils.issues | commands.issues.usage |

## zenutils

| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |
| --- | --- | --- | --- | --- |
| /book_of_logic | — | 0 | command.zenutils.book_of_logic | commands.book_of_logic.usage |
| /bugs | — | 0 | command.zenutils.bugs | commands.issues.usage |
| /curseforge | — | 0 | command.zenutils.curseforge | commands.curseforge.usage |
| /discord | — | 0 | command.zenutils.discord | commands.discord.usage |
| /introduction_book | — | 0 | command.zenutils.introduction_book | commands.introduction_book.usage |
| /issues | — | 0 | command.zenutils.issues | commands.issues.usage |

## Все параметры рангов

Пустой override означает использование наследования/заводского значения.

| Node | Заводской игрок | Заводской OP | Наш тестовый player override |
| --- | --- | --- | --- |
| default_op_rank | false | false | — |
| default_player_rank | false | false | true |
| ftbutilities.afk.timer | 0s | 0s | — |
| ftbutilities.back.cooldown | 3m | 0s | — |
| ftbutilities.back.warmup | 5s | 0s | — |
| ftbutilities.badge |  |  | — |
| ftbutilities.chat.name_format | &lt;{name}&gt; | &lt;&amp;2{name}&amp;r&gt; | — |
| ftbutilities.chat.text.color | white | white | — |
| ftbutilities.chunkloader.max_chunks | 50 | 64 | — |
| ftbutilities.claims.max_chunks | 100 | 1000 | — |
| ftbutilities.homes.cooldown | 5m | 0s | 10s |
| ftbutilities.homes.max | 1 | 100 | 3 |
| ftbutilities.homes.warmup | 5s | 0s | 3s |
| ftbutilities.rtp.cooldown | 10m | 0s | — |
| ftbutilities.rtp.warmup | 5s | 0s | — |
| ftbutilities.spawn.cooldown | 1m | 0s | — |
| ftbutilities.spawn.warmup | 5s | 0s | — |
| ftbutilities.tpa.cooldown | 3m | 0s | — |
| ftbutilities.tpa.warmup | 5s | 0s | — |
| ftbutilities.warps.cooldown | 1m | 0s | — |
| ftbutilities.warps.warmup | 5s | 0s | — |
| parent |  |  | — |
| power | 0 | 0 | 1 |

## Дополнительные зарегистрированные права

ALL — доступно обычному игроку по умолчанию, OP — оператору, NONE — явно не выдаётся.
Эта таблица дополняет command nodes выше и не заменяет проверки внутри команд.

| Node | Заводской доступ | Описание API |
| --- | --- | --- |
| admin_panel.ftbutilities.crash_reports.delete | OP | Allow to delete crash reports, requires admin_panel.ftbutilities.crash_reports.view |
| admin_panel.ftbutilities.crash_reports.view | OP | Allow to view crash reports via Admin Panel |
| admin_panel.ftbutilities.edit_world.gamerules | OP | Allow to edit gamerules via Admin Panel |
| betterquesting.command.admin | OP | admin commmand permission |
| betterquesting.command.admin.complete | OP | Permission to force completes a quest for the given user |
| betterquesting.command.admin.default | OP | Permission to saves/loads the current quest database to/from the global default directory |
| betterquesting.command.admin.delete | OP | Permission to delete given quest(s) and progression data however it does not delete new world defaults |
| betterquesting.command.admin.edit | OP | Permission to activate quest editing mode on and off |
| betterquesting.command.admin.hardcore | OP | Permission to activate or not the use of hardcore lives |
| betterquesting.command.admin.lives | OP | Permission to set lives to the given user |
| betterquesting.command.admin.purge | OP | Permission to purge all hidden quests and progression data however it does not delete any in new world defaults |
| betterquesting.command.admin.reset | OP | Permission to erases quest completion data for the given user |
| betterquesting.command.user | ALL | user commmand permission |
| betterquesting.command.user.hardcores | ALL | Permission to manually resyncs the local questing database with the server in case of potential desync issues |
| betterquesting.command.user.help | ALL | Permission to execute command which gives the player a copy of the in game starter guide. |
| betterquesting.command.user.refresh | ALL | Permission to manually resync the local questing database with the server in case of potential desync issues |
| block.tap | ALL | Node for taping blocks with the tree tap |
| block.wrench | ALL | Node for wrenching blocks |
| enderio.attack.block_killer_joe | ALL | Permission for the block block_killer_joe of Ender IO to attack entities. Note: The GameProfile will be for the block owner, the EntityPlayer in the context will be the fake player. |
| enderio.attract.tile.block_attractor_obelisk | ALL | Permission for the block tile.block_attractor_obelisk of Ender IO to attract entities. Note: The GameProfile will be for the block owner, the EntityPlayer in the context will be the fake player. |
| enderio.creative_spawner.edit | OP | Permission to edit the creative spawner&#x27;s settings. |
| enderio.farm.tile.block_farm_station | ALL | Permission for the block tile.block_farm_station of Ender IO to farm land. This includes tilling, planting, harvesting and fertilizing. Only the base block of a plant will be checked, not the dirt block below it or the additional plant blocks above it. Note: The GameProfile will be for the block owner, the EntityPlayer in the context will be the fake player. |
| enderio.gui.block_advanced_power_monitor | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_advanced_power_monitor |
| enderio.gui.block_alloy_smelter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_alloy_smelter |
| enderio.gui.block_attractor_obelisk | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_attractor_obelisk |
| enderio.gui.block_aversion_obelisk | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_aversion_obelisk |
| enderio.gui.block_buffer | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_buffer |
| enderio.gui.block_cap_bank | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_cap_bank |
| enderio.gui.block_combustion_generator | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_combustion_generator |
| enderio.gui.block_conduit_bundle | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_conduit_bundle |
| enderio.gui.block_crafter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_crafter |
| enderio.gui.block_creative_spawner | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_creative_spawner |
| enderio.gui.block_dark_paper_anvil | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_dark_paper_anvil |
| enderio.gui.block_dark_steel_anvil | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_dark_steel_anvil |
| enderio.gui.block_dialing_device | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_dialing_device |
| enderio.gui.block_enchanter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_enchanter |
| enderio.gui.block_ender_generator | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_ender_generator |
| enderio.gui.block_enhanced_alloy_smelter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_enhanced_alloy_smelter |
| enderio.gui.block_enhanced_combustion_generator | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_enhanced_combustion_generator |
| enderio.gui.block_enhanced_sag_mill | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_enhanced_sag_mill |
| enderio.gui.block_enhanced_vat | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_enhanced_vat |
| enderio.gui.block_enhanced_wired_charger | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_enhanced_wired_charger |
| enderio.gui.block_experience_obelisk | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_experience_obelisk |
| enderio.gui.block_farm_station | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_farm_station |
| enderio.gui.block_franken_zombie_generator | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_franken_zombie_generator |
| enderio.gui.block_impulse_hopper | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_impulse_hopper |
| enderio.gui.block_inhibitor_obelisk | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_inhibitor_obelisk |
| enderio.gui.block_inventory_chest_big | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_inventory_chest_big |
| enderio.gui.block_inventory_chest_enormous | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_inventory_chest_enormous |
| enderio.gui.block_inventory_chest_huge | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_inventory_chest_huge |
| enderio.gui.block_inventory_chest_large | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_inventory_chest_large |
| enderio.gui.block_inventory_chest_medium | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_inventory_chest_medium |
| enderio.gui.block_inventory_chest_small | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_inventory_chest_small |
| enderio.gui.block_inventory_chest_tiny | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_inventory_chest_tiny |
| enderio.gui.block_inventory_chest_warehouse | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_inventory_chest_warehouse |
| enderio.gui.block_inventory_chest_warehouse13 | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_inventory_chest_warehouse13 |
| enderio.gui.block_inventory_panel | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_inventory_panel |
| enderio.gui.block_inventory_panel_sensor | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_inventory_panel_sensor |
| enderio.gui.block_killer_joe | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_killer_joe |
| enderio.gui.block_lava_generator | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_lava_generator |
| enderio.gui.block_niard | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_niard |
| enderio.gui.block_painter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_painter |
| enderio.gui.block_power_monitor | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_power_monitor |
| enderio.gui.block_powered_spawner | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_powered_spawner |
| enderio.gui.block_relocator_obelisk | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_relocator_obelisk |
| enderio.gui.block_sag_mill | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_sag_mill |
| enderio.gui.block_simple_alloy_smelter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_simple_alloy_smelter |
| enderio.gui.block_simple_crafter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_simple_crafter |
| enderio.gui.block_simple_furnace | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_simple_furnace |
| enderio.gui.block_simple_sag_mill | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_simple_sag_mill |
| enderio.gui.block_simple_stirling_generator | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_simple_stirling_generator |
| enderio.gui.block_simple_wired_charger | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_simple_wired_charger |
| enderio.gui.block_slice_and_splice | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_slice_and_splice |
| enderio.gui.block_soul_binder | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_soul_binder |
| enderio.gui.block_stirling_generator | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_stirling_generator |
| enderio.gui.block_tank | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_tank |
| enderio.gui.block_tele_pad | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_tele_pad |
| enderio.gui.block_transceiver | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_transceiver |
| enderio.gui.block_travel_anchor | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_travel_anchor |
| enderio.gui.block_vacuum_chest | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_vacuum_chest |
| enderio.gui.block_vat | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_vat |
| enderio.gui.block_weather_obelisk | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_weather_obelisk |
| enderio.gui.block_wired_charger | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_wired_charger |
| enderio.gui.block_xp_vacuum | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_xp_vacuum |
| enderio.gui.block_zombie_generator | ALL | Permission to open the GUI(s) of Ender IO&#x27;s block_zombie_generator |
| enderio.gui.item_advanced_item_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_advanced_item_filter |
| enderio.gui.item_basic_item_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_basic_item_filter |
| enderio.gui.item_big_advanced_item_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_big_advanced_item_filter |
| enderio.gui.item_big_item_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_big_item_filter |
| enderio.gui.item_dark_steel_boots | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_dark_steel_boots |
| enderio.gui.item_dark_steel_chestplate | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_dark_steel_chestplate |
| enderio.gui.item_dark_steel_helmet | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_dark_steel_helmet |
| enderio.gui.item_dark_steel_leggings | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_dark_steel_leggings |
| enderio.gui.item_enchantment_filter_big | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_enchantment_filter_big |
| enderio.gui.item_enchantment_filter_normal | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_enchantment_filter_normal |
| enderio.gui.item_end_steel_boots | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_end_steel_boots |
| enderio.gui.item_end_steel_chestplate | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_end_steel_chestplate |
| enderio.gui.item_end_steel_helmet | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_end_steel_helmet |
| enderio.gui.item_end_steel_leggings | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_end_steel_leggings |
| enderio.gui.item_existing_item_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_existing_item_filter |
| enderio.gui.item_fluid_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_fluid_filter |
| enderio.gui.item_gas_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_gas_filter |
| enderio.gui.item_inventory_remote | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_inventory_remote |
| enderio.gui.item_limited_item_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_limited_item_filter |
| enderio.gui.item_mod_item_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_mod_item_filter |
| enderio.gui.item_power_item_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_power_item_filter |
| enderio.gui.item_redstone_and_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_redstone_and_filter |
| enderio.gui.item_redstone_counting_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_redstone_counting_filter |
| enderio.gui.item_redstone_nand_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_redstone_nand_filter |
| enderio.gui.item_redstone_nor_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_redstone_nor_filter |
| enderio.gui.item_redstone_not_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_redstone_not_filter |
| enderio.gui.item_redstone_or_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_redstone_or_filter |
| enderio.gui.item_redstone_sensor_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_redstone_sensor_filter |
| enderio.gui.item_redstone_timer_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_redstone_timer_filter |
| enderio.gui.item_redstone_toggle_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_redstone_toggle_filter |
| enderio.gui.item_redstone_xnor_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_redstone_xnor_filter |
| enderio.gui.item_redstone_xor_filter | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_redstone_xor_filter |
| enderio.gui.item_soul_filter_big | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_soul_filter_big |
| enderio.gui.item_soul_filter_normal | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_soul_filter_normal |
| enderio.gui.item_stellar_alloy_boots | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_stellar_alloy_boots |
| enderio.gui.item_stellar_alloy_chestplate | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_stellar_alloy_chestplate |
| enderio.gui.item_stellar_alloy_helmet | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_stellar_alloy_helmet |
| enderio.gui.item_stellar_alloy_leggings | ALL | Permission to open the GUI(s) of Ender IO&#x27;s item_stellar_alloy_leggings |
| enderio.soulvial.pickup | ALL | Permission to pickup an entity with Ender IO&#x27;s soul vessel |
| enderio.soulvial.pickup_owned | OP | Permission to pickup an entity that is owned by another player with Ender IO&#x27;s soul vessel |
| enderio.soulvial.place | ALL | Permission to place down an entity with Ender IO&#x27;s soul vessel |
| enderio.wrench.break.block_advanced_power_monitor | ALL | Permission to wrench-break the block block_advanced_power_monitor of Ender IO |
| enderio.wrench.break.block_alloy_smelter | ALL | Permission to wrench-break the block block_alloy_smelter of Ender IO |
| enderio.wrench.break.block_attractor_obelisk | ALL | Permission to wrench-break the block block_attractor_obelisk of Ender IO |
| enderio.wrench.break.block_aversion_obelisk | ALL | Permission to wrench-break the block block_aversion_obelisk of Ender IO |
| enderio.wrench.break.block_buffer | ALL | Permission to wrench-break the block block_buffer of Ender IO |
| enderio.wrench.break.block_cap_bank | ALL | Permission to wrench-break the block block_cap_bank of Ender IO |
| enderio.wrench.break.block_combustion_generator | ALL | Permission to wrench-break the block block_combustion_generator of Ender IO |
| enderio.wrench.break.block_conduit_bundle | ALL | Permission to wrench-break the block block_conduit_bundle of Ender IO |
| enderio.wrench.break.block_crafter | ALL | Permission to wrench-break the block block_crafter of Ender IO |
| enderio.wrench.break.block_creative_spawner | OP | Permission to wrench-break the block block_creative_spawner of Ender IO |
| enderio.wrench.break.block_detector_block | ALL | Permission to wrench-break the block block_detector_block of Ender IO |
| enderio.wrench.break.block_detector_block_silent | ALL | Permission to wrench-break the block block_detector_block_silent of Ender IO |
| enderio.wrench.break.block_dialing_device | ALL | Permission to wrench-break the block block_dialing_device of Ender IO |
| enderio.wrench.break.block_electric_light | ALL | Permission to wrench-break the block block_electric_light of Ender IO |
| enderio.wrench.break.block_enchanter | ALL | Permission to wrench-break the block block_enchanter of Ender IO |
| enderio.wrench.break.block_ender_generator | ALL | Permission to wrench-break the block block_ender_generator of Ender IO |
| enderio.wrench.break.block_enderman_skull | ALL | Permission to wrench-break the block block_enderman_skull of Ender IO |
| enderio.wrench.break.block_enhanced_alloy_smelter | ALL | Permission to wrench-break the block block_enhanced_alloy_smelter of Ender IO |
| enderio.wrench.break.block_enhanced_alloy_smelter_top | ALL | Permission to wrench-break the block block_enhanced_alloy_smelter_top of Ender IO |
| enderio.wrench.break.block_enhanced_combustion_generator | ALL | Permission to wrench-break the block block_enhanced_combustion_generator of Ender IO |
| enderio.wrench.break.block_enhanced_combustion_generator_top | ALL | Permission to wrench-break the block block_enhanced_combustion_generator_top of Ender IO |
| enderio.wrench.break.block_enhanced_sag_mill | ALL | Permission to wrench-break the block block_enhanced_sag_mill of Ender IO |
| enderio.wrench.break.block_enhanced_sag_mill_top | ALL | Permission to wrench-break the block block_enhanced_sag_mill_top of Ender IO |
| enderio.wrench.break.block_enhanced_vat | ALL | Permission to wrench-break the block block_enhanced_vat of Ender IO |
| enderio.wrench.break.block_enhanced_vat_top | ALL | Permission to wrench-break the block block_enhanced_vat_top of Ender IO |
| enderio.wrench.break.block_enhanced_wired_charger | ALL | Permission to wrench-break the block block_enhanced_wired_charger of Ender IO |
| enderio.wrench.break.block_enhanced_wired_charger_top | ALL | Permission to wrench-break the block block_enhanced_wired_charger_top of Ender IO |
| enderio.wrench.break.block_enhanced_wireless_charger | ALL | Permission to wrench-break the block block_enhanced_wireless_charger of Ender IO |
| enderio.wrench.break.block_experience_obelisk | ALL | Permission to wrench-break the block block_experience_obelisk of Ender IO |
| enderio.wrench.break.block_farm_station | ALL | Permission to wrench-break the block block_farm_station of Ender IO |
| enderio.wrench.break.block_franken_zombie_generator | ALL | Permission to wrench-break the block block_franken_zombie_generator of Ender IO |
| enderio.wrench.break.block_gauge | ALL | Permission to wrench-break the block block_gauge of Ender IO |
| enderio.wrench.break.block_holier_fog | ALL | Permission to wrench-break the block block_holier_fog of Ender IO |
| enderio.wrench.break.block_holy_fog | ALL | Permission to wrench-break the block block_holy_fog of Ender IO |
| enderio.wrench.break.block_impulse_hopper | ALL | Permission to wrench-break the block block_impulse_hopper of Ender IO |
| enderio.wrench.break.block_industrial_insulation | ALL | Permission to wrench-break the block block_industrial_insulation of Ender IO |
| enderio.wrench.break.block_infinity_fog | ALL | Permission to wrench-break the block block_infinity_fog of Ender IO |
| enderio.wrench.break.block_inhibitor_obelisk | ALL | Permission to wrench-break the block block_inhibitor_obelisk of Ender IO |
| enderio.wrench.break.block_inventory_chest_big | ALL | Permission to wrench-break the block block_inventory_chest_big of Ender IO |
| enderio.wrench.break.block_inventory_chest_enormous | ALL | Permission to wrench-break the block block_inventory_chest_enormous of Ender IO |
| enderio.wrench.break.block_inventory_chest_huge | ALL | Permission to wrench-break the block block_inventory_chest_huge of Ender IO |
| enderio.wrench.break.block_inventory_chest_large | ALL | Permission to wrench-break the block block_inventory_chest_large of Ender IO |
| enderio.wrench.break.block_inventory_chest_medium | ALL | Permission to wrench-break the block block_inventory_chest_medium of Ender IO |
| enderio.wrench.break.block_inventory_chest_small | ALL | Permission to wrench-break the block block_inventory_chest_small of Ender IO |
| enderio.wrench.break.block_inventory_chest_tiny | ALL | Permission to wrench-break the block block_inventory_chest_tiny of Ender IO |
| enderio.wrench.break.block_inventory_chest_warehouse | ALL | Permission to wrench-break the block block_inventory_chest_warehouse of Ender IO |
| enderio.wrench.break.block_inventory_chest_warehouse13 | ALL | Permission to wrench-break the block block_inventory_chest_warehouse13 of Ender IO |
| enderio.wrench.break.block_inventory_panel | ALL | Permission to wrench-break the block block_inventory_panel of Ender IO |
| enderio.wrench.break.block_inventory_panel_sensor | ALL | Permission to wrench-break the block block_inventory_panel_sensor of Ender IO |
| enderio.wrench.break.block_killer_joe | ALL | Permission to wrench-break the block block_killer_joe of Ender IO |
| enderio.wrench.break.block_lava_generator | ALL | Permission to wrench-break the block block_lava_generator of Ender IO |
| enderio.wrench.break.block_light_node | ALL | Permission to wrench-break the block block_light_node of Ender IO |
| enderio.wrench.break.block_niard | ALL | Permission to wrench-break the block block_niard of Ender IO |
| enderio.wrench.break.block_normal_wireless_charger | ALL | Permission to wrench-break the block block_normal_wireless_charger of Ender IO |
| enderio.wrench.break.block_omni_reservoir | ALL | Permission to wrench-break the block block_omni_reservoir of Ender IO |
| enderio.wrench.break.block_painter | ALL | Permission to wrench-break the block block_painter of Ender IO |
| enderio.wrench.break.block_power_monitor | ALL | Permission to wrench-break the block block_power_monitor of Ender IO |
| enderio.wrench.break.block_powered_spawner | ALL | Permission to wrench-break the block block_powered_spawner of Ender IO |
| enderio.wrench.break.block_relocator_obelisk | ALL | Permission to wrench-break the block block_relocator_obelisk of Ender IO |
| enderio.wrench.break.block_reservoir | ALL | Permission to wrench-break the block block_reservoir of Ender IO |
| enderio.wrench.break.block_sag_mill | ALL | Permission to wrench-break the block block_sag_mill of Ender IO |
| enderio.wrench.break.block_simple_alloy_smelter | ALL | Permission to wrench-break the block block_simple_alloy_smelter of Ender IO |
| enderio.wrench.break.block_simple_crafter | ALL | Permission to wrench-break the block block_simple_crafter of Ender IO |
| enderio.wrench.break.block_simple_furnace | ALL | Permission to wrench-break the block block_simple_furnace of Ender IO |
| enderio.wrench.break.block_simple_sag_mill | ALL | Permission to wrench-break the block block_simple_sag_mill of Ender IO |
| enderio.wrench.break.block_simple_stirling_generator | ALL | Permission to wrench-break the block block_simple_stirling_generator of Ender IO |
| enderio.wrench.break.block_simple_wired_charger | ALL | Permission to wrench-break the block block_simple_wired_charger of Ender IO |
| enderio.wrench.break.block_slice_and_splice | ALL | Permission to wrench-break the block block_slice_and_splice of Ender IO |
| enderio.wrench.break.block_solar_panel | ALL | Permission to wrench-break the block block_solar_panel of Ender IO |
| enderio.wrench.break.block_soul_binder | ALL | Permission to wrench-break the block block_soul_binder of Ender IO |
| enderio.wrench.break.block_stirling_generator | ALL | Permission to wrench-break the block block_stirling_generator of Ender IO |
| enderio.wrench.break.block_tank | ALL | Permission to wrench-break the block block_tank of Ender IO |
| enderio.wrench.break.block_tele_pad | ALL | Permission to wrench-break the block block_tele_pad of Ender IO |
| enderio.wrench.break.block_transceiver | ALL | Permission to wrench-break the block block_transceiver of Ender IO |
| enderio.wrench.break.block_travel_anchor | ALL | Permission to wrench-break the block block_travel_anchor of Ender IO |
| enderio.wrench.break.block_vacuum_chest | ALL | Permission to wrench-break the block block_vacuum_chest of Ender IO |
| enderio.wrench.break.block_vat | ALL | Permission to wrench-break the block block_vat of Ender IO |
| enderio.wrench.break.block_weather_obelisk | ALL | Permission to wrench-break the block block_weather_obelisk of Ender IO |
| enderio.wrench.break.block_wired_charger | ALL | Permission to wrench-break the block block_wired_charger of Ender IO |
| enderio.wrench.break.block_wireless_charger | ALL | Permission to wrench-break the block block_wireless_charger of Ender IO |
| enderio.wrench.break.block_wireless_charger_extension | ALL | Permission to wrench-break the block block_wireless_charger_extension of Ender IO |
| enderio.wrench.break.block_xp_vacuum | ALL | Permission to wrench-break the block block_xp_vacuum of Ender IO |
| enderio.wrench.break.block_zombie_generator | ALL | Permission to wrench-break the block block_zombie_generator of Ender IO |
| enderio.wrench.iomode.block_advanced_power_monitor | ALL | Permission to set IO mode by wrench-clicking the block block_advanced_power_monitor of Ender IO |
| enderio.wrench.iomode.block_alloy_smelter | ALL | Permission to set IO mode by wrench-clicking the block block_alloy_smelter of Ender IO |
| enderio.wrench.iomode.block_attractor_obelisk | ALL | Permission to set IO mode by wrench-clicking the block block_attractor_obelisk of Ender IO |
| enderio.wrench.iomode.block_aversion_obelisk | ALL | Permission to set IO mode by wrench-clicking the block block_aversion_obelisk of Ender IO |
| enderio.wrench.iomode.block_buffer | ALL | Permission to set IO mode by wrench-clicking the block block_buffer of Ender IO |
| enderio.wrench.iomode.block_cap_bank | ALL | Permission to set IO mode by wrench-clicking the block block_cap_bank of Ender IO |
| enderio.wrench.iomode.block_combustion_generator | ALL | Permission to set IO mode by wrench-clicking the block block_combustion_generator of Ender IO |
| enderio.wrench.iomode.block_conduit_bundle | ALL | Permission to set IO mode by wrench-clicking the block block_conduit_bundle of Ender IO |
| enderio.wrench.iomode.block_crafter | ALL | Permission to set IO mode by wrench-clicking the block block_crafter of Ender IO |
| enderio.wrench.iomode.block_creative_spawner | OP | Permission to set IO mode by wrench-clicking the block block_creative_spawner of Ender IO |
| enderio.wrench.iomode.block_detector_block | ALL | Permission to set IO mode by wrench-clicking the block block_detector_block of Ender IO |
| enderio.wrench.iomode.block_detector_block_silent | ALL | Permission to set IO mode by wrench-clicking the block block_detector_block_silent of Ender IO |
| enderio.wrench.iomode.block_dialing_device | ALL | Permission to set IO mode by wrench-clicking the block block_dialing_device of Ender IO |
| enderio.wrench.iomode.block_electric_light | ALL | Permission to set IO mode by wrench-clicking the block block_electric_light of Ender IO |
| enderio.wrench.iomode.block_enchanter | ALL | Permission to set IO mode by wrench-clicking the block block_enchanter of Ender IO |
| enderio.wrench.iomode.block_ender_generator | ALL | Permission to set IO mode by wrench-clicking the block block_ender_generator of Ender IO |
| enderio.wrench.iomode.block_enderman_skull | ALL | Permission to set IO mode by wrench-clicking the block block_enderman_skull of Ender IO |
| enderio.wrench.iomode.block_enhanced_alloy_smelter | ALL | Permission to set IO mode by wrench-clicking the block block_enhanced_alloy_smelter of Ender IO |
| enderio.wrench.iomode.block_enhanced_alloy_smelter_top | ALL | Permission to set IO mode by wrench-clicking the block block_enhanced_alloy_smelter_top of Ender IO |
| enderio.wrench.iomode.block_enhanced_combustion_generator | ALL | Permission to set IO mode by wrench-clicking the block block_enhanced_combustion_generator of Ender IO |
| enderio.wrench.iomode.block_enhanced_combustion_generator_top | ALL | Permission to set IO mode by wrench-clicking the block block_enhanced_combustion_generator_top of Ender IO |
| enderio.wrench.iomode.block_enhanced_sag_mill | ALL | Permission to set IO mode by wrench-clicking the block block_enhanced_sag_mill of Ender IO |
| enderio.wrench.iomode.block_enhanced_sag_mill_top | ALL | Permission to set IO mode by wrench-clicking the block block_enhanced_sag_mill_top of Ender IO |
| enderio.wrench.iomode.block_enhanced_vat | ALL | Permission to set IO mode by wrench-clicking the block block_enhanced_vat of Ender IO |
| enderio.wrench.iomode.block_enhanced_vat_top | ALL | Permission to set IO mode by wrench-clicking the block block_enhanced_vat_top of Ender IO |
| enderio.wrench.iomode.block_enhanced_wired_charger | ALL | Permission to set IO mode by wrench-clicking the block block_enhanced_wired_charger of Ender IO |
| enderio.wrench.iomode.block_enhanced_wired_charger_top | ALL | Permission to set IO mode by wrench-clicking the block block_enhanced_wired_charger_top of Ender IO |
| enderio.wrench.iomode.block_enhanced_wireless_charger | ALL | Permission to set IO mode by wrench-clicking the block block_enhanced_wireless_charger of Ender IO |
| enderio.wrench.iomode.block_experience_obelisk | ALL | Permission to set IO mode by wrench-clicking the block block_experience_obelisk of Ender IO |
| enderio.wrench.iomode.block_farm_station | ALL | Permission to set IO mode by wrench-clicking the block block_farm_station of Ender IO |
| enderio.wrench.iomode.block_franken_zombie_generator | ALL | Permission to set IO mode by wrench-clicking the block block_franken_zombie_generator of Ender IO |
| enderio.wrench.iomode.block_gauge | ALL | Permission to set IO mode by wrench-clicking the block block_gauge of Ender IO |
| enderio.wrench.iomode.block_holier_fog | ALL | Permission to set IO mode by wrench-clicking the block block_holier_fog of Ender IO |
| enderio.wrench.iomode.block_holy_fog | ALL | Permission to set IO mode by wrench-clicking the block block_holy_fog of Ender IO |
| enderio.wrench.iomode.block_impulse_hopper | ALL | Permission to set IO mode by wrench-clicking the block block_impulse_hopper of Ender IO |
| enderio.wrench.iomode.block_industrial_insulation | ALL | Permission to set IO mode by wrench-clicking the block block_industrial_insulation of Ender IO |
| enderio.wrench.iomode.block_infinity_fog | ALL | Permission to set IO mode by wrench-clicking the block block_infinity_fog of Ender IO |
| enderio.wrench.iomode.block_inhibitor_obelisk | ALL | Permission to set IO mode by wrench-clicking the block block_inhibitor_obelisk of Ender IO |
| enderio.wrench.iomode.block_inventory_chest_big | ALL | Permission to set IO mode by wrench-clicking the block block_inventory_chest_big of Ender IO |
| enderio.wrench.iomode.block_inventory_chest_enormous | ALL | Permission to set IO mode by wrench-clicking the block block_inventory_chest_enormous of Ender IO |
| enderio.wrench.iomode.block_inventory_chest_huge | ALL | Permission to set IO mode by wrench-clicking the block block_inventory_chest_huge of Ender IO |
| enderio.wrench.iomode.block_inventory_chest_large | ALL | Permission to set IO mode by wrench-clicking the block block_inventory_chest_large of Ender IO |
| enderio.wrench.iomode.block_inventory_chest_medium | ALL | Permission to set IO mode by wrench-clicking the block block_inventory_chest_medium of Ender IO |
| enderio.wrench.iomode.block_inventory_chest_small | ALL | Permission to set IO mode by wrench-clicking the block block_inventory_chest_small of Ender IO |
| enderio.wrench.iomode.block_inventory_chest_tiny | ALL | Permission to set IO mode by wrench-clicking the block block_inventory_chest_tiny of Ender IO |
| enderio.wrench.iomode.block_inventory_chest_warehouse | ALL | Permission to set IO mode by wrench-clicking the block block_inventory_chest_warehouse of Ender IO |
| enderio.wrench.iomode.block_inventory_chest_warehouse13 | ALL | Permission to set IO mode by wrench-clicking the block block_inventory_chest_warehouse13 of Ender IO |
| enderio.wrench.iomode.block_inventory_panel | ALL | Permission to set IO mode by wrench-clicking the block block_inventory_panel of Ender IO |
| enderio.wrench.iomode.block_inventory_panel_sensor | ALL | Permission to set IO mode by wrench-clicking the block block_inventory_panel_sensor of Ender IO |
| enderio.wrench.iomode.block_killer_joe | ALL | Permission to set IO mode by wrench-clicking the block block_killer_joe of Ender IO |
| enderio.wrench.iomode.block_lava_generator | ALL | Permission to set IO mode by wrench-clicking the block block_lava_generator of Ender IO |
| enderio.wrench.iomode.block_light_node | ALL | Permission to set IO mode by wrench-clicking the block block_light_node of Ender IO |
| enderio.wrench.iomode.block_niard | ALL | Permission to set IO mode by wrench-clicking the block block_niard of Ender IO |
| enderio.wrench.iomode.block_normal_wireless_charger | ALL | Permission to set IO mode by wrench-clicking the block block_normal_wireless_charger of Ender IO |
| enderio.wrench.iomode.block_omni_reservoir | ALL | Permission to set IO mode by wrench-clicking the block block_omni_reservoir of Ender IO |
| enderio.wrench.iomode.block_painter | ALL | Permission to set IO mode by wrench-clicking the block block_painter of Ender IO |
| enderio.wrench.iomode.block_power_monitor | ALL | Permission to set IO mode by wrench-clicking the block block_power_monitor of Ender IO |
| enderio.wrench.iomode.block_powered_spawner | ALL | Permission to set IO mode by wrench-clicking the block block_powered_spawner of Ender IO |
| enderio.wrench.iomode.block_relocator_obelisk | ALL | Permission to set IO mode by wrench-clicking the block block_relocator_obelisk of Ender IO |
| enderio.wrench.iomode.block_reservoir | ALL | Permission to set IO mode by wrench-clicking the block block_reservoir of Ender IO |
| enderio.wrench.iomode.block_sag_mill | ALL | Permission to set IO mode by wrench-clicking the block block_sag_mill of Ender IO |
| enderio.wrench.iomode.block_simple_alloy_smelter | ALL | Permission to set IO mode by wrench-clicking the block block_simple_alloy_smelter of Ender IO |
| enderio.wrench.iomode.block_simple_crafter | ALL | Permission to set IO mode by wrench-clicking the block block_simple_crafter of Ender IO |
| enderio.wrench.iomode.block_simple_furnace | ALL | Permission to set IO mode by wrench-clicking the block block_simple_furnace of Ender IO |
| enderio.wrench.iomode.block_simple_sag_mill | ALL | Permission to set IO mode by wrench-clicking the block block_simple_sag_mill of Ender IO |
| enderio.wrench.iomode.block_simple_stirling_generator | ALL | Permission to set IO mode by wrench-clicking the block block_simple_stirling_generator of Ender IO |
| enderio.wrench.iomode.block_simple_wired_charger | ALL | Permission to set IO mode by wrench-clicking the block block_simple_wired_charger of Ender IO |
| enderio.wrench.iomode.block_slice_and_splice | ALL | Permission to set IO mode by wrench-clicking the block block_slice_and_splice of Ender IO |
| enderio.wrench.iomode.block_solar_panel | ALL | Permission to set IO mode by wrench-clicking the block block_solar_panel of Ender IO |
| enderio.wrench.iomode.block_soul_binder | ALL | Permission to set IO mode by wrench-clicking the block block_soul_binder of Ender IO |
| enderio.wrench.iomode.block_stirling_generator | ALL | Permission to set IO mode by wrench-clicking the block block_stirling_generator of Ender IO |
| enderio.wrench.iomode.block_tank | ALL | Permission to set IO mode by wrench-clicking the block block_tank of Ender IO |
| enderio.wrench.iomode.block_tele_pad | ALL | Permission to set IO mode by wrench-clicking the block block_tele_pad of Ender IO |
| enderio.wrench.iomode.block_transceiver | ALL | Permission to set IO mode by wrench-clicking the block block_transceiver of Ender IO |
| enderio.wrench.iomode.block_travel_anchor | ALL | Permission to set IO mode by wrench-clicking the block block_travel_anchor of Ender IO |
| enderio.wrench.iomode.block_vacuum_chest | ALL | Permission to set IO mode by wrench-clicking the block block_vacuum_chest of Ender IO |
| enderio.wrench.iomode.block_vat | ALL | Permission to set IO mode by wrench-clicking the block block_vat of Ender IO |
| enderio.wrench.iomode.block_weather_obelisk | ALL | Permission to set IO mode by wrench-clicking the block block_weather_obelisk of Ender IO |
| enderio.wrench.iomode.block_wired_charger | ALL | Permission to set IO mode by wrench-clicking the block block_wired_charger of Ender IO |
| enderio.wrench.iomode.block_wireless_charger | ALL | Permission to set IO mode by wrench-clicking the block block_wireless_charger of Ender IO |
| enderio.wrench.iomode.block_wireless_charger_extension | ALL | Permission to set IO mode by wrench-clicking the block block_wireless_charger_extension of Ender IO |
| enderio.wrench.iomode.block_xp_vacuum | ALL | Permission to set IO mode by wrench-clicking the block block_xp_vacuum of Ender IO |
| enderio.wrench.iomode.block_zombie_generator | ALL | Permission to set IO mode by wrench-clicking the block block_zombie_generator of Ender IO |
| ftbutilities.back.back | OP | Allow player back to last time where /back is used |
| ftbutilities.back.home | OP | Allow player back to last time where /home is used |
| ftbutilities.back.infinite | NONE | Allow to use &#x27;back&#x27; command infinite times |
| ftbutilities.back.respawn | ALL | Allow player back to last death point |
| ftbutilities.back.rtp | OP | Allow player back to last time where /rtp is used |
| ftbutilities.back.spawn | OP | Allow player back to last time where /spawn is used |
| ftbutilities.back.tpa | OP | Allow player back to last time where /tpa is used |
| ftbutilities.back.warp | OP | Allow player back to last time where /warp is used |
| ftbutilities.chat.formatting | ALL | Allows to use **bold**, *italic* and ~~striketrough~~ in chat |
| ftbutilities.chat.nickname.colors | OP | Allow to use formatting codes in nickname, requires ftbutilities.chat.nickname.set |
| ftbutilities.chat.nickname.set | OP | Allow to change nickname |
| ftbutilities.chat.speak | ALL | Controls if player is muted or not |
| ftbutilities.chunkloader.load_offline | ALL | Keep loaded chunks working when player goes offline |
| ftbutilities.claims.attack_animals | OP | Allow to attack animals in claimed chunks |
| ftbutilities.claims.bypass_limits | NONE | Allow to bypass claiming and loading limits |
| ftbutilities.display.admin_info | OP | Display &#x27;Admin&#x27; in Server Info |
| ftbutilities.homes.cross_dim | ALL | Can use /home to teleport to/from another dimension |
| ftbutilities.leaderboard.ftbutilities.deaths | ALL |  |
| ftbutilities.leaderboard.ftbutilities.deaths_per_hour | ALL |  |
| ftbutilities.leaderboard.ftbutilities.jumps | ALL |  |
| ftbutilities.leaderboard.ftbutilities.last_seen | ALL |  |
| ftbutilities.leaderboard.ftbutilities.mob_kills | ALL |  |
| ftbutilities.leaderboard.ftbutilities.time_played | ALL |  |
| ftbutilities.other_player.claims.claim | OP | Allow player to claim other team chunks |
| ftbutilities.other_player.claims.load | OP | Allow player to load other team chunks |
| ftbutilities.other_player.claims.see_info | OP | Allow player to see info of other team chunks |
| ftbutilities.other_player.claims.unclaim | OP | Allow player to unclaim other team chunks |
| ftbutilities.other_player.claims.unload | OP | Allow player to unload other team chunks |
| ftbutilities.other_player.heal | OP | Allow to heal other players |
| ftbutilities.other_player.homes.list | OP | Allow to list other people homes |
| ftbutilities.other_player.homes.teleport | OP | Allow to teleport to other people homes |
| ftbutilities.tpa.cross_dim | ALL | Can use /tpa to teleport to/from another dimension |
| galacticraft.station.create | ALL | Allows players to create space stations |
| spark | OP | Access to the spark command |

## Повторяющиеся права блоков и предметов

Индивидуальные записи этой группы сведены в семейства. Точные исключения
содержатся в registry.json; полный сырой снимок создаётся в локальном стенде.

| Шаблон | Записей | Заводские уровни |
| --- | --- | --- |
| ftbutilities.claims.block.edit.* | 5786 | {&#x27;OP&#x27;: 5786} |
| ftbutilities.claims.block.interact.* | 5786 | {&#x27;OP&#x27;: 5713, &#x27;ALL&#x27;: 73} |
| ftbutilities.claims.item.* | 10236 | {&#x27;ALL&#x27;: 10227, &#x27;OP&#x27;: 9} |
