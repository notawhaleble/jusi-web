-- Run by pytest with an isolated home, real service/kernel and a fake browser host.
vim.opt.packpath = { vim.env.VIMRUNTIME }
vim.opt.runtimepath = { vim.env.JUSI_SOURCE_ROOT, vim.env.VIMRUNTIME }
vim.o.columns, vim.o.lines = 150, 50
local jusi = require('jusi')
local python = vim.env.JUSI_WEB_TEST_PYTHON
local notifications, pages = {}, {}
vim.notify = function(message) table.insert(notifications, tostring(message)) end
vim.api.nvim_create_user_command('JusiWebBuffer', function(command)
  local buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_set_current_buf(buf)
  table.insert(pages, { buf = buf, url = command.args })
end, { nargs = '?' })
jusi.setup({ terminal_bridge_command = { python, '-m', 'jusi', 'terminal-bridge' } })
local notebook, service
local debug_record
local function wait(predicate, message)
  io.stderr:write('web e2e: ' .. message .. '\n')
  io.stderr:flush()
  local done = vim.wait(15000, predicate, 10)
  local screen = debug_record and vim.api.nvim_buf_is_valid(debug_record.buf)
    and table.concat(vim.api.nvim_buf_get_lines(debug_record.buf, 0, -1, false), '\n') or ''
  assert(done, message .. '\n' .. table.concat(notifications, '\n') .. '\n' .. screen)
end
local function text(record)
  return table.concat(vim.api.nvim_buf_get_lines(record.buf, 0, -1, false), '\n')
end
local ok, failure = xpcall(function()
  notebook = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_set_current_buf(notebook)
  vim.api.nvim_buf_set_lines(notebook, 0, -1, false, {
    '╭──', '%%web', '', '╰──', '╭──', '%%web', 'https://keep.test', '╰──',
  })
  service = jusi.start_service({ buf = notebook,
    command = { python, '-m', 'jusi', 'serve', '--config', vim.env.JUSI_WEB_TEST_CONFIG }, timeout_ms = 10000 })
  wait(function() return jusi._sessions[notebook] and jusi._sessions[notebook].controller.transport_state == 'connected' end, 'connect')
  local session = jusi._sessions[notebook]
  jusi.start_kernel(notebook)
  wait(function() return session.controller.kernel_state == 'on' end, 'start kernel')
  local first_id, second_id = session.model:cell_at_row(1).id, session.model:cell_at_row(5).id
  jusi.bootstrap(notebook, 1)
  local record
  wait(function()
    for _, current in pairs(session.interactive.surfaces) do
      if current.client.cell_id == first_id then record = current; return text(record):find('Python docs', 1, true) end
    end
  end, 'bootstrap bookmarks')
  local client_id, terminal_buf, surface_id = record.client.client_id, record.buf, record.surface.surface_id
  local plugin_window = assert(require('jusi.presentation.window').find(terminal_buf))
  debug_record = record
  local function submit(body, expected_failure)
    local snapshot = session.model:cell_snapshot(first_id)
    vim.api.nvim_buf_set_lines(notebook, snapshot.body_start_row, snapshot.body_end_row, false, { '%%web', body })
    session.model:flush()
    local done, response, err
    jusi.followup(notebook, session.model:cell_snapshot(first_id).open_row + 1, function(r, e)
      done, response, err = true, r, e
    end)
    wait(function() return done end, 'followup: ' .. body)
    if expected_failure then assert(err, 'search error was swallowed') else assert(not err, vim.inspect(err)) end
    assert(session.controller.clients[client_id] and session.interactive.surfaces[surface_id].buf == terminal_buf)
    return response
  end
  submit('py')
  wait(function() return text(record):find('web:bookmarks:py', 1, true) end, 'ambiguous bookmarks sheet')
  -- A followup arriving after the UI has gone idle must also redraw itself.
  vim.wait(1500, function() return false end, 10)
  submit('find cheese websites')
  wait(function() return text(record):find('citation-a.test', 1, true) end, 'citation sheet')
  vim.api.nvim_chan_send(record.job_id, '\r')
  wait(function() return #pages == 1 end, 'open citation')
  assert(pages[1].url == 'https://citation-a.test')
  local first_page = pages[1].buf
  assert(vim.api.nvim_win_get_buf(plugin_window) == first_page, 'page did not use the plugin window')
  assert(#vim.api.nvim_list_wins() == 2, 'page created an extra split')
  -- Native page close/hide preserves the exact plugin client and result sheet.
  vim.api.nvim_buf_delete(first_page, { force = true })
  assert(session.controller.clients[client_id] and vim.api.nvim_buf_is_valid(terminal_buf))
  assert(jusi.toggle_focus(notebook, session.model:cell_snapshot(first_id).open_row + 1) == terminal_buf)
  plugin_window = assert(require('jusi.presentation.window').find(terminal_buf))
  vim.api.nvim_chan_send(record.job_id, 'j\r')
  wait(function() return #pages == 2 end, 'open another citation after close')
  assert(pages[2].url == 'https://citation-b.test')
  assert(vim.api.nvim_win_get_buf(plugin_window) == pages[2].buf and #vim.api.nvim_list_wins() == 2)
  local second_page = pages[2].buf
  submit('Python docs')
  wait(function() return #pages == 3 end, 'bookmark followup')
  assert(pages[3].url == 'https://docs.test' and not vim.api.nvim_buf_is_valid(second_page))
  assert(vim.api.nvim_win_get_buf(plugin_window) == pages[3].buf)
  local third_page = pages[3].buf
  submit('')
  assert(not vim.api.nvim_buf_is_valid(third_page) and #pages == 3, 'list followup retained a page')
  assert(vim.api.nvim_win_get_buf(plugin_window) == terminal_buf, 'list followup did not restore VisiData')
  -- A separate cell has separate replacement authority.
  local second_snapshot = session.model:cell_snapshot(second_id)
  jusi.execute(notebook, second_snapshot.open_row + 1)
  wait(function() return #pages == 4 end, 'second client page')
  local retained = pages[4].buf
  local second_record
  wait(function()
    for _, current in pairs(session.interactive.surfaces) do
      if current.client.cell_id == second_id then
        second_record = current
        local screen = text(current)
        return screen:find('last_opened', 1, true) and screen:find('https://keep.test', 1, true)
      end
    end
  end, 'initial direct URL in history')
  vim.api.nvim_chan_send(second_record.job_id, 'e\001\011Kept page\r')
  wait(function() return text(second_record):find('Kept page', 1, true) end, 'bookmark initial direct URL')
  submit('https://next.test')
  wait(function() return #pages == 5 end, 'first client new page')
  assert(vim.api.nvim_buf_is_valid(retained), 'followup closed another cell page')
  local replaced = pages[5].buf
  submit('break search', true)
  assert(not vim.api.nvim_buf_is_valid(replaced) and vim.api.nvim_buf_is_valid(retained))
  submit('https://recovered.test')
  wait(function() return #pages == 6 end, 'recover after API error')
  -- An application open can replace its page while its terminal is hidden.
  wait(function()
    local screen = text(record)
    return screen:find('last_opened', 1, true) and screen:find('https://recovered.test', 1, true)
  end, 'followup direct URL in history')
  vim.api.nvim_chan_send(record.job_id, 'e\001\011Recovered page\r')
  wait(function() return text(record):find('Recovered page', 1, true) end, 'bookmark followup direct URL')
  local count = #vim.api.nvim_list_wins()
  vim.api.nvim_chan_send(record.job_id, '\r')
  wait(function() return #pages == 7 end, 'replace page while terminal is hidden')
  assert(pages[7].url == 'https://recovered.test' and #vim.api.nvim_list_wins() == count)
  assert(vim.api.nvim_win_get_buf(plugin_window) == pages[7].buf)
  assert(not vim.api.nvim_buf_is_valid(pages[6].buf), 'drilldown retained its previous page')
  -- Neither the page nor its terminal needs to be visible for replacement.
  local unrelated = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_win_set_buf(plugin_window, unrelated)
  vim.api.nvim_chan_send(record.job_id, '\r')
  wait(function() return #pages == 8 end, 'replace fully hidden page')
  assert(not vim.api.nvim_buf_is_valid(pages[7].buf), 'hidden page survived replacement')
  assert(vim.api.nvim_win_get_buf(plugin_window) == unrelated, 'repurposed window was overwritten')
  -- Move the new page to another tab, then reopen by bookmark from the notebook.
  local hidden_page = pages[8].buf
  local page_window = assert(require('jusi.presentation.window').find(hidden_page))
  vim.api.nvim_set_current_win(page_window)
  vim.cmd('tab split')
  local other_tab = vim.api.nvim_get_current_tabpage()
  vim.api.nvim_win_close(page_window, true)
  vim.api.nvim_set_current_win(plugin_window)
  submit('Recovered page')
  wait(function() return #pages == 9 end, 'replace bookmark page in another tab')
  assert(not vim.api.nvim_buf_is_valid(hidden_page), 'other-tab page survived bookmark open')
  assert(vim.api.nvim_win_get_tabpage(assert(require('jusi.presentation.window').find(pages[9].buf))) == other_tab)
  -- A direct URL must retire the same slot even when hidden in every tab.
  local latest_window = assert(require('jusi.presentation.window').find(pages[9].buf))
  vim.api.nvim_win_set_buf(latest_window, unrelated)
  vim.api.nvim_set_current_win(plugin_window)
  submit('https://recovered.test')
  wait(function() return #pages == 10 end, 'direct URL replaces hidden bookmark page')
  assert(not vim.api.nvim_buf_is_valid(pages[9].buf))
  assert(vim.api.nvim_win_get_buf(latest_window) == unrelated)
  plugin_window = assert(require('jusi.presentation.window').find(pages[10].buf))
  -- Worker-returned URL actions share ownership with application drilldowns.
  vim.api.nvim_win_set_buf(plugin_window, unrelated)
  jusi.editor_action('open_url', { buf = notebook,
    row = session.model:cell_snapshot(first_id).open_row + 1,
    selection = { text = 'https://editor-action.test' } })
  wait(function() return #pages == 11 end, 'editor URL action replaces hidden page')
  assert(not vim.api.nvim_buf_is_valid(pages[10].buf))
  assert(vim.api.nvim_win_get_buf(plugin_window) == unrelated)
  plugin_window = assert(require('jusi.presentation.window').find(pages[11].buf))
  -- Serialize behind the application's acknowledged open/history update.
  submit('')
  assert(vim.api.nvim_win_get_buf(plugin_window) == terminal_buf)
  for index, page in ipairs(pages) do
    assert(vim.api.nvim_buf_is_valid(page.buf) == (index == 4), 'unexpected retained page ' .. index)
  end
  assert(session.controller.kernel_state == 'on')
  assert(session.interactive.surfaces[surface_id].buf == terminal_buf)
  jusi.stop_service(notebook)
  wait(function() return service.state == 'stopped' and not jusi._sessions[notebook] end, 'service cleanup')
end, debug.traceback)
if notebook and jusi._sessions[notebook] then jusi._destroy_session(notebook)
elseif service and service.state ~= 'stopped' then service:stop() end
if not ok then io.stderr:write(failure .. '\n'); vim.cmd('cquit 1') end
print('jusi-web real service/kernel/VisiData/Neovim lifecycle passed')
vim.cmd('qa!')
