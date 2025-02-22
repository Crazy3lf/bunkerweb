local class     = require "middleclass"
local plugin    = require "bunkerweb.plugin"
local utils     = require "bunkerweb.utils"
local ipmatcher = require "resty.ipmatcher"

local greylist  = class("greylist", plugin)

function greylist:initialize(ctx)
	-- Call parent initialize
	plugin.initialize(self, "greylist", ctx)
	-- Decode lists
	if ngx.get_phase() ~= "init" and self:is_needed() then
		local lists, err = self.datastore:get("plugin_greylist_lists", true)
		if not lists then
			self.logger:log(ngx.ERR, err)
			self.lists = {}
		else
			self.lists = lists
		end
		local kinds = {
			["IP"] = {},
			["RDNS"] = {},
			["ASN"] = {},
			["USER_AGENT"] = {},
			["URI"] = {}
		}
		for kind, _ in pairs(kinds) do
			for data in self.variables["GREYLIST_" .. kind]:gmatch("%S+") do
				if not self.lists[kind] then
					self.lists[kind] = {}
				end
				table.insert(self.lists[kind], data)
			end
		end
	end
end

function greylist:is_needed()
	-- Loading case
	if self.is_loading then
		return false
	end
	-- Request phases (no default)
	if self.is_request and (self.ctx.bw.server_name ~= "_") then
		return self.variables["USE_GREYLIST"] == "yes"
	end
	-- Other cases : at least one service uses it
	local is_needed, err = utils.has_variable("USE_GREYLIST", "yes")
	if is_needed == nil then
		self.logger:log(ngx.ERR, "can't check USE_GREYLIST variable : " .. err)
	end
	return is_needed
end

function greylist:init()
	-- Check if init needed
	if not self:is_needed() then
		return self:ret(true, "init not needed")
	end
	-- Read greylists
	local greylists = {
		["IP"] = {},
		["RDNS"] = {},
		["ASN"] = {},
		["USER_AGENT"] = {},
		["URI"] = {},
	}
	local i = 0
	for kind, _ in pairs(greylists) do
		local f, err = io.open("/var/cache/bunkerweb/greylist/" .. kind .. ".list", "r")
		if f then
			for line in f:lines() do
				table.insert(greylists[kind], line)
				i = i + 1
			end
			f:close()
		end
	end
	-- Load them into datastore
	local ok, err = self.datastore:set("plugin_greylist_lists", greylists, nil, true)
	if not ok then
		return self:ret(false, "can't store greylist list into datastore : " .. err)
	end
	return self:ret(true, "successfully loaded " .. tostring(i) .. " bad IP/network/rDNS/ASN/User-Agent/URI")
end

function greylist:access()
	-- Check if access is needed
	if not self:is_needed() then
		return self:ret(true, "access not needed")
	end
	-- Check the caches
	local checks = {
		["IP"] = "ip" .. self.ctx.bw.remote_addr
	}
	if self.ctx.bw.http_user_agent then
		checks["UA"] = "ua" .. self.ctx.bw.http_user_agent
	end
	if self.ctx.bw.uri then
		checks["URI"] = "uri" .. self.ctx.bw.uri
	end
	local already_cached = {
		["IP"] = false,
		["URI"] = false,
		["UA"] = false
	}
	for k, v in pairs(checks) do
		local ok, cached = self:is_in_cache(v)
		if not ok then
			self.logger:log(ngx.ERR, "error while checking cache : " .. cached)
		elseif cached and cached ~= "ko" then
			return self:ret(true, k .. " is in cached greylist (info : " .. cached .. ")")
		end
		if ok and cached then
			already_cached[k] = true
		end
	end
	-- Check lists
	if not self.lists then
		return self:ret(false, "lists is nil")
	end
	-- Perform checks
	for k, v in pairs(checks) do
		if not already_cached[k] then
			local ok, greylisted = self:is_greylisted(k)
			if ok == nil then
				self.logger:log(ngx.ERR, "error while checking if " .. k .. " is greylisted : " .. greylisted)
			else
				local ok, err = self:add_to_cache(self:kind_to_ele(k), greylisted)
				if not ok then
					self.logger:log(ngx.ERR, "error while adding element to cache : " .. err)
				end
				if greylisted ~= "ko" then
					return self:ret(true, k .. " is in greylist")
				end
			end
		end
	end

	-- Return
	return self:ret(true, "not in greylist", utils.get_deny_status(self.ctx))
end

function greylist:preread()
	return self:access()
end

function greylist:kind_to_ele(kind)
	if kind == "IP" then
		return "ip" .. self.ctx.bw.remote_addr
	elseif kind == "UA" then
		return "ua" .. self.ctx.bw.http_user_agent
	elseif kind == "URI" then
		return "uri" .. self.ctx.bw.uri
	end
end

function greylist:is_greylisted(kind)
	if kind == "IP" then
		return self:is_greylisted_ip()
	elseif kind == "URI" then
		return self:is_greylisted_uri()
	elseif kind == "UA" then
		return self:is_greylisted_ua()
	end
	return false, "unknown kind " .. kind
end

function greylist:is_greylisted_ip()
	-- Check if IP is in greylist
	local ipm, err = ipmatcher.new(self.lists["IP"])
	if not ipm then
		return nil, err
	end
	local match, err = ipm:match(self.ctx.bw.remote_addr)
	if err then
		return nil, err
	end
	if match then
		return true, "ip"
	end

	-- Check if rDNS is needed
	local check_rdns = true
	if self.variables["GREYLIST_RDNS_GLOBAL"] == "yes" and not self.ctx.bw.ip_is_global then
		check_rdns = false
	end
	if check_rdns then
		-- Get rDNS
		local rdns_list, err = utils.get_rdns(self.ctx.bw.remote_addr)
		-- Check if rDNS is in greylist
		if rdns_list then
			for i, rdns in ipairs(rdns_list) do
				for j, suffix in ipairs(self.lists["RDNS"]) do
					if rdns:sub(- #suffix) == suffix then
						return true, "rDNS " .. suffix
					end
				end
			end
		else
			self.logger:log(ngx.ERR, "error while getting rdns : " .. err)
		end
	end

	-- Check if ASN is in greylist
	if self.ctx.bw.ip_is_global then
		local asn, err = utils.get_asn(self.ctx.bw.remote_addr)
		if not asn then
			self.logger:log(ngx.ERR, "can't get ASN of IP " .. self.ctx.bw.remote_addr .. " : " .. err)
		else
			for i, bl_asn in ipairs(self.lists["ASN"]) do
				if bl_asn == tostring(asn) then
					return true, "ASN " .. bl_asn
				end
			end
		end
	end

	-- Not greylisted
	return false, "ko"
end

function greylist:is_greylisted_uri()
	-- Check if URI is in greylist
	for i, uri in ipairs(self.lists["URI"]) do
		if utils.regex_match(self.ctx.bw.uri, uri) then
			return true, "URI " .. uri
		end
	end
	-- URI is not greylisted
	return false, "ko"
end

function greylist:is_greylisted_ua()
	-- Check if UA is in greylist
	for i, ua in ipairs(self.lists["USER_AGENT"]) do
		if utils.regex_match(self.ctx.bw.http_user_agent, ua) then
			return true, "UA " .. ua
		end
	end
	-- UA is not greylisted
	return false, "ko"
end

function greylist:is_in_cache(ele)
	local ok, data = self.cachestore:get("plugin_greylist_" .. self.ctx.bw.server_name .. ele)
	if not ok then
		return false, data
	end
	return true, data
end

function greylist:add_to_cache(ele, value)
	local ok, err = self.cachestore:set("plugin_greylist_" .. self.ctx.bw.server_name .. ele, value, 86400)
	if not ok then
		return false, err
	end
	return true
end

return greylist
