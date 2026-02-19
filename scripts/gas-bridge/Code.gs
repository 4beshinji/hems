/**
 * HEMS GAS Bridge — Google Apps Script Web App
 *
 * Deploy as Web App (Execute as: Me, Access: Anyone with link).
 * Set Script Property "API_KEY" for authentication.
 *
 * Usage: GET https://script.google.com/macros/s/{DEPLOY_ID}/exec?key=KEY&action=ACTION
 */

// --- Authentication ---

function _checkAuth(e) {
  const key = (e && e.parameter && e.parameter.key) || '';
  const expected = PropertiesService.getScriptProperties().getProperty('API_KEY') || '';
  if (!expected || key !== expected) {
    return ContentService.createTextOutput(
      JSON.stringify({ error: 'unauthorized' })
    ).setMimeType(ContentService.MimeType.JSON);
  }
  return null;
}

// --- Main Handler ---

function doGet(e) {
  const authError = _checkAuth(e);
  if (authError) return authError;

  const action = (e.parameter.action || 'health').toLowerCase();

  try {
    let result;
    switch (action) {
      case 'health':
        result = _health();
        break;
      case 'calendar_today':
        result = _calendarToday();
        break;
      case 'calendar_upcoming':
        result = _calendarUpcoming(parseInt(e.parameter.hours) || 24);
        break;
      case 'calendar_free_slots':
        result = _calendarFreeSlots(parseInt(e.parameter.hours) || 12);
        break;
      case 'tasks_list':
        result = _tasksList();
        break;
      case 'tasks_due_today':
        result = _tasksDueToday();
        break;
      case 'gmail_summary':
        result = _gmailSummary();
        break;
      case 'gmail_recent':
        result = _gmailRecent(parseInt(e.parameter.count) || 10);
        break;
      case 'sheets_read':
        result = _sheetsRead(e.parameter.id, e.parameter.sheet, e.parameter.range);
        break;
      case 'drive_recent':
        result = _driveRecent(parseInt(e.parameter.count) || 20);
        break;
      default:
        result = { error: 'unknown_action', action: action };
    }
    return ContentService.createTextOutput(
      JSON.stringify(result)
    ).setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(
      JSON.stringify({ error: err.message })
    ).setMimeType(ContentService.MimeType.JSON);
  }
}

// --- Health ---

function _health() {
  return {
    status: 'ok',
    timestamp: new Date().toISOString(),
    quotaRemaining: MailApp.getRemainingDailyQuota(),
  };
}

// --- Calendar ---

function _formatEvent(event) {
  return {
    id: event.getId(),
    title: event.getTitle(),
    start: event.getStartTime().toISOString(),
    end: event.getEndTime().toISOString(),
    location: event.getLocation() || '',
    isAllDay: event.isAllDayEvent(),
    description: (event.getDescription() || '').substring(0, 200),
    calendarName: event.getOriginalCalendarId
      ? '' : '',
  };
}

function _calendarToday() {
  var now = new Date();
  var start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  var end = new Date(start.getTime() + 24 * 60 * 60 * 1000);

  var events = [];
  var calendars = CalendarApp.getAllCalendars();
  for (var i = 0; i < calendars.length; i++) {
    var cal = calendars[i];
    var calEvents = cal.getEvents(start, end);
    for (var j = 0; j < calEvents.length; j++) {
      var ev = _formatEvent(calEvents[j]);
      ev.calendarName = cal.getName();
      events.push(ev);
    }
  }
  events.sort(function(a, b) { return a.start.localeCompare(b.start); });
  return { events: events, date: start.toISOString().split('T')[0] };
}

function _calendarUpcoming(hours) {
  var now = new Date();
  var end = new Date(now.getTime() + hours * 60 * 60 * 1000);

  var events = [];
  var calendars = CalendarApp.getAllCalendars();
  for (var i = 0; i < calendars.length; i++) {
    var cal = calendars[i];
    var calEvents = cal.getEvents(now, end);
    for (var j = 0; j < calEvents.length; j++) {
      var ev = _formatEvent(calEvents[j]);
      ev.calendarName = cal.getName();
      events.push(ev);
    }
  }
  events.sort(function(a, b) { return a.start.localeCompare(b.start); });
  return { events: events, hours: hours };
}

function _calendarFreeSlots(hours) {
  var now = new Date();
  var end = new Date(now.getTime() + hours * 60 * 60 * 1000);

  // Collect all busy periods
  var busy = [];
  var calendars = CalendarApp.getAllCalendars();
  for (var i = 0; i < calendars.length; i++) {
    var calEvents = calendars[i].getEvents(now, end);
    for (var j = 0; j < calEvents.length; j++) {
      if (!calEvents[j].isAllDayEvent()) {
        busy.push({
          start: calEvents[j].getStartTime().getTime(),
          end: calEvents[j].getEndTime().getTime(),
        });
      }
    }
  }

  // Sort and merge overlapping
  busy.sort(function(a, b) { return a.start - b.start; });
  var merged = [];
  for (var i = 0; i < busy.length; i++) {
    if (merged.length > 0 && busy[i].start <= merged[merged.length - 1].end) {
      merged[merged.length - 1].end = Math.max(merged[merged.length - 1].end, busy[i].end);
    } else {
      merged.push({ start: busy[i].start, end: busy[i].end });
    }
  }

  // Find free slots (minimum 30 minutes)
  var slots = [];
  var cursor = now.getTime();
  for (var i = 0; i < merged.length; i++) {
    if (merged[i].start > cursor) {
      var duration = Math.round((merged[i].start - cursor) / 60000);
      if (duration >= 30) {
        slots.push({
          start: new Date(cursor).toISOString(),
          end: new Date(merged[i].start).toISOString(),
          duration_minutes: duration,
        });
      }
    }
    cursor = Math.max(cursor, merged[i].end);
  }
  // Trailing free slot
  if (cursor < end.getTime()) {
    var duration = Math.round((end.getTime() - cursor) / 60000);
    if (duration >= 30) {
      slots.push({
        start: new Date(cursor).toISOString(),
        end: end.toISOString(),
        duration_minutes: duration,
      });
    }
  }

  return { slots: slots, hours: hours };
}

// --- Google Tasks ---

function _tasksList() {
  var taskLists = Tasks.Tasklists.list().getItems() || [];
  var result = [];
  for (var i = 0; i < taskLists.length; i++) {
    var tl = taskLists[i];
    var tasks = [];
    try {
      var items = Tasks.Tasks.list(tl.getId()).getItems() || [];
      for (var j = 0; j < items.length; j++) {
        var t = items[j];
        tasks.push({
          id: t.getId(),
          title: t.getTitle(),
          notes: t.getNotes() || '',
          due: t.getDue() || '',
          status: t.getStatus(),
        });
      }
    } catch (e) {
      // Skip inaccessible task lists
    }
    result.push({
      id: tl.getId(),
      title: tl.getTitle(),
      tasks: tasks,
    });
  }
  return { taskLists: result };
}

function _tasksDueToday() {
  var now = new Date();
  var todayEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59);
  var taskLists = Tasks.Tasklists.list().getItems() || [];
  var result = [];

  for (var i = 0; i < taskLists.length; i++) {
    var tl = taskLists[i];
    var tasks = [];
    try {
      var items = Tasks.Tasks.list(tl.getId()).getItems() || [];
      for (var j = 0; j < items.length; j++) {
        var t = items[j];
        if (t.getStatus() === 'completed') continue;
        var due = t.getDue();
        if (!due) continue;
        var dueDate = new Date(due);
        var isOverdue = dueDate < now;
        var isDueToday = dueDate <= todayEnd;
        if (isOverdue || isDueToday) {
          tasks.push({
            id: t.getId(),
            title: t.getTitle(),
            notes: t.getNotes() || '',
            due: due,
            status: t.getStatus(),
            is_overdue: isOverdue,
            list_name: tl.getTitle(),
          });
        }
      }
    } catch (e) {
      // Skip
    }
    if (tasks.length > 0) {
      result.push({ id: tl.getId(), title: tl.getTitle(), tasks: tasks });
    }
  }
  return { taskLists: result };
}

// --- Gmail ---

function _gmailSummary() {
  var labels = {};
  // INBOX
  var inbox = GmailApp.getInboxThreads(0, 1);
  labels['INBOX'] = {
    unread: GmailApp.getInboxUnreadCount(),
    total: null, // Total requires expensive call; skip
  };

  // User labels
  var userLabels = GmailApp.getUserLabels();
  for (var i = 0; i < userLabels.length; i++) {
    var label = userLabels[i];
    var unread = label.getUnreadCount();
    if (unread > 0) {
      labels[label.getName()] = { unread: unread, total: null };
    }
  }

  return { labels: labels };
}

function _gmailRecent(count) {
  var threads = GmailApp.getInboxThreads(0, Math.min(count, 50));
  var result = [];
  for (var i = 0; i < threads.length; i++) {
    var t = threads[i];
    var firstMsg = t.getMessages()[0];
    result.push({
      id: t.getId(),
      subject: t.getFirstMessageSubject(),
      from: firstMsg ? firstMsg.getFrom() : '',
      date: t.getLastMessageDate().toISOString(),
      labels: t.getLabels().map(function(l) { return l.getName(); }),
      unread: t.isUnread(),
      messageCount: t.getMessageCount(),
    });
  }
  return { threads: result };
}

// --- Google Sheets ---

function _sheetsRead(fileId, sheetName, range) {
  if (!fileId) return { error: 'missing parameter: id' };

  var ss = SpreadsheetApp.openById(fileId);
  var sheet = sheetName ? ss.getSheetByName(sheetName) : ss.getActiveSheet();
  if (!sheet) return { error: 'sheet not found: ' + sheetName };

  var data;
  if (range) {
    data = sheet.getRange(range).getValues();
  } else {
    data = sheet.getDataRange().getValues();
  }

  var headers = data.length > 0 ? data[0].map(String) : [];
  var values = data.length > 1 ? data.slice(1) : [];

  return {
    spreadsheet: ss.getName(),
    sheet: sheet.getName(),
    headers: headers,
    values: values.map(function(row) {
      return row.map(function(cell) {
        if (cell instanceof Date) return cell.toISOString();
        return cell;
      });
    }),
    rowCount: values.length,
  };
}

// --- Google Drive ---

function _driveRecent(count) {
  var files = DriveApp.getFiles();
  var result = [];
  var collected = 0;

  // DriveApp.getFiles() returns in unspecified order;
  // collect and sort by last updated
  var all = [];
  var limit = Math.min(count * 3, 200); // Over-fetch to sort
  while (files.hasNext() && all.length < limit) {
    var f = files.next();
    all.push({
      name: f.getName(),
      mimeType: f.getMimeType(),
      modifiedTime: f.getLastUpdated().toISOString(),
      url: f.getUrl(),
      size: f.getSize(),
    });
  }

  all.sort(function(a, b) { return b.modifiedTime.localeCompare(a.modifiedTime); });
  return { files: all.slice(0, count) };
}
