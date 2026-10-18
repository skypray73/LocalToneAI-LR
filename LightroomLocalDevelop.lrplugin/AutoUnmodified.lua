local LrPathUtils=import 'LrPathUtils'
local run=dofile(LrPathUtils.child(_PLUGIN.path,'AutoCore.lua'))
run{onlyUnmodified=true}
