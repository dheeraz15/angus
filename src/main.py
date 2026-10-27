"""Apify actor port of nebraska_import.py, for any set of states.

Fetches the angus.org breeder search for each state, then each breeder's
contact popup, one results page at a time. Each breeder becomes one dataset
item with the same columns as the Apps Script tab; export the dataset as CSV
from the run's Storage tab. Progress is kept in the run's key-value store
(STATE), so a migrated or resurrected run continues where it stopped.
"""
import asyncio
import html as htmllib
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from apify import Actor, Event
from curl_cffi.requests import AsyncSession

ALL_STATES = ('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH '
              'NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY').split()
BASE = 'https://www.angus.org'
HEADERS = ['Breeder ID', 'Name', 'Member Code', 'Location', 'State',
           'Contact Details', 'Phones', 'Emails', 'Websites', 'Status', 'Updated']
MAX_CONSECUTIVE_ERRORS = 3


def first_url(state):
    return BASE + '/find-a-breeder?' + urlencode({
        'MemberSearchRequest.ctlStateCt.Value': state + '    ',
        'MemberSearchRequest.sCity': '', 'MemberSearchRequest.sZip': '',
        'MemberSearchRequest.sName': '', 'MemberSearchRequest.sMemCodeOne': '',
        'irs': '9999', 'SuppressNonSevere': 'true'})


async def request(session, url, **kw):
    kw['headers'] = {'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.9', **kw.get('headers', {})}
    r = await session.request(kw.pop('method', 'GET'), url, impersonate='chrome124', timeout=60, **kw)
    if not 200 <= r.status_code < 300:
        raise RuntimeError('Angus HTTP %d. Session may have expired or requests may be blocked.' % r.status_code)
    return r.text


def attrs(tag):
    return {k.lower(): htmllib.unescape(v)
            for k, _, v in re.findall(r'([\w:.-]+)\s*=\s*(["\'])([\s\S]*?)\2', tag)}


def text(fragment):
    fragment = re.sub(r'<script\b[^>]*>[\s\S]*?</script>', '', fragment, flags=re.I)
    fragment = re.sub(r'<br\s*/?\s*>|</(?:div|p|li)>', '\n', fragment, flags=re.I)
    fragment = htmllib.unescape(re.sub(r'<[^>]*>', '', fragment))
    lines = (re.sub(r'\s+', ' ', s).strip() for s in re.split(r'\r?\n', fragment))
    return '\n'.join(s for s in lines if s)


def token(page):
    for tag in re.findall(r'<input\b[^>]*>', page, flags=re.I):
        a = attrs(tag)
        if a.get('name') in ('AntiforgeryFieldname', '__RequestVerificationToken'):
            return a.get('value', '')
    return ''


def breeders(page):
    result, seen = [], set()
    for row in re.findall(r'<tr\b[^>]*>[\s\S]*?</tr>', page, flags=re.I):
        m = re.search(r'data-custcode\s*=\s*["\'](\d+)["\']', row, flags=re.I)
        if not m or m.group(1) in seen:
            continue
        cells = re.findall(r'<td\b[^>]*>[\s\S]*?</td>', row, flags=re.I)
        name_code = text(cells[0] if cells else '')
        code = re.search(r'\b[A-Z]-\d+\b', name_code)
        result.append({'id': m.group(1),
                       'name': re.sub(r'\b[A-Z]-\d+\b', '', name_code, count=1).strip(),
                       'code': code.group(0) if code else '',
                       'location': text(cells[1] if len(cells) > 1 else '')})
        seen.add(m.group(1))
    return result


def contact(fragment):
    t = text(fragment)
    unique = lambda xs: '\n'.join(dict.fromkeys(xs))
    links = [attrs(tag).get('href', '') for tag in re.findall(r'<a\b[^>]*>', fragment, flags=re.I)]
    return {
        'text': t,
        'phones': unique(m.group(0) for m in re.finditer(
            r'(?:\+1[ .-]?)?(?:\(\d{3}\)|\b\d{3})[ .-]?\d{3}[ .-]?\d{4}(?:\s*(?:ext\.?|x)\s*\d+)?', t, flags=re.I)),
        'emails': unique(re.findall(r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}', t + ' ' + fragment, flags=re.I)),
        'websites': unique(h for h in links if re.match(r'https?://', h, flags=re.I))}


def safe(v):
    # Prevent scraped text from becoming a spreadsheet formula in the CSV export.
    return "'" + v if isinstance(v, str) and re.match(r'^[=+@-]', v) else v


def make_row(b, state, c, status):
    return dict(zip(HEADERS, map(safe, [b['id'], b['name'], b['code'], b['location'], state,
        c.get('text', ''), c.get('phones', ''), c.get('emails', ''), c.get('websites', ''),
        status, datetime.now(timezone.utc).isoformat(timespec='seconds')])))


def next_url(page):
    start = re.search(r'<input\b[^>]*name=["\']PageRequest\.sSortColumn["\']', page, flags=re.I)
    if not start:
        raise RuntimeError('Paging form not found.')
    form = re.split(r'</form\s*>', page[start.start():], flags=re.I)[0]
    params = {}
    for tag in re.findall(r'<input\b[^>]*>', form, flags=re.I):
        a = attrs(tag)
        if a.get('type') == 'hidden' and a.get('name'):
            params[a['name']] = a.get('value', '')
    button = next((a for a in map(attrs, re.findall(r'<button\b[^>]*>', form, flags=re.I))
                   if a.get('name') == 'PageRequest.GridNextPage'), None)
    if not button:
        raise RuntimeError('Next-page control not found.')
    params['PageRequest.GridNextPage'] = button.get('value') or '1'
    params['irs'] = '9999'
    params['SuppressNonSevere'] = 'true'
    return BASE + '/find-a-breeder?' + urlencode(params)


def is_empty_search(page):
    # Only accept explicit empty-result text on an otherwise valid search page.
    return (re.search(r'Showing\s+0\s+out\s+of\s+0\s+record|\bno\s+(?:records|results|members)\s+(?:were\s+)?found\b',
                      text(page), flags=re.I)
            and token(page)
            and re.search(r'name=["\']MemberSearchRequest\.ctlStateCt\.Value["\']', page, flags=re.I))


def next_state(run):
    run['state_index'] += 1
    if run['state_index'] < len(run['states']):
        st = run['states'][run['state_index']]
        run.update(next_url=first_url(st), expected_page=1)
    else:
        run['next_url'] = None


async def import_page(session, run, done, settings):
    """Imports one results page. Returns False once maxBreeders is reached."""
    url, state = run['next_url'], run['states'][run['state_index']]
    page = await request(session, url)
    if run['expected_page'] == 1 and not breeders(page) and is_empty_search(page):
        Actor.log.info('%s: no breeders found', state)
        next_state(run)
        return True
    m = re.search(r'Page:\s*(\d+)\s*of\s*(\d+)', page, flags=re.I)
    if not m:
        raise RuntimeError('Results page not recognized. Angus may have returned a security challenge or changed its HTML.')
    current, total = int(m.group(1)), int(m.group(2))
    if current != run['expected_page']:
        raise RuntimeError('Pagination failed: expected page %d, received %d' % (run['expected_page'], current))
    tok = token(page)
    if not tok:
        raise RuntimeError('CSRF token missing from results page.')
    found = breeders(page)
    if not found:
        raise RuntimeError('No breeder IDs found on results page %d' % current)
    for b in found:
        if b['id'] in done:
            continue
        if settings['max'] and run['pushed'] >= settings['max']:
            return False
        await asyncio.sleep(settings['delay'])
        try:
            fragment = await request(session, BASE + '/Account/BreederContact', method='POST',
                data={'breederId': b['id']},
                headers={'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                         'X-CSRF-TOKEN-HEADERNAME': tok, 'X-Requested-With': 'XMLHttpRequest',
                         'Origin': BASE, 'Referer': url})
            if re.search(r'<!doctype|<html\b|<script\b|<iframe\b|captcha|access denied', fragment, flags=re.I):
                raise RuntimeError('Unexpected contact response: possible login/security page.')
            if not fragment.strip() or 'Search error' in fragment:
                row = make_row(b, state, {}, 'OK (no contact)')
            elif not re.search(r'<div\b', fragment, flags=re.I):
                raise RuntimeError('Contact response format not recognized: ' + repr(fragment[:200]))
            else:
                row = make_row(b, state, contact(fragment), 'OK')
        except Exception as e:
            Actor.log.warning('Breeder %s error: %s', b['id'], e)
            if not run['errors']:
                # If this streak ends the run, the resumed run restarts from this page.
                run['retry_from'] = {'next_url': url, 'expected_page': current, 'state_index': run['state_index']}
            run['errors'].append(make_row(b, state, {}, 'ERROR: %s' % e))
            if len(run['errors']) >= MAX_CONSECUTIVE_ERRORS:
                # Stop instead of repeatedly requesting a blocked endpoint. The failed
                # breeders are not marked done, so a resumed run retries them.
                raise RuntimeError('%d contact requests failed in a row; stopping. Last error: %s'
                                   % (len(run['errors']), e))
            continue
        # A success means earlier failures were isolated: record them as ERROR rows.
        for failed in run['errors'] + [row]:
            await Actor.push_data(failed)
            done.add(failed['Breeder ID'])
            run['pushed'] += 1
        run['errors'] = []
    if current >= total:
        Actor.log.info('%s: complete (%d pages)', state, total)
        next_state(run)
    else:
        run.update(next_url=next_url(page), expected_page=current + 1)
        Actor.log.info('%s: finished page %d of %d (%d breeders this run)', state, current, total, run['pushed'])
    return True


async def main():
    async with Actor:
        actor_input = await Actor.get_input() or {}
        run = await Actor.get_value('STATE')
        if run:
            Actor.log.info('Resuming from saved state: %s page %d',
                           run['states'][run['state_index']] if run['next_url'] else '-', run['expected_page'])
        else:
            states = [s.strip().upper() for s in actor_input.get('states') or [] if s.strip()] or ALL_STATES
            unknown = [s for s in states if s not in ALL_STATES]
            if unknown:
                await Actor.fail(status_message='Unknown state code(s): ' + ', '.join(unknown))
                return
            run = {'states': states, 'state_index': 0, 'next_url': first_url(states[0]),
                   'expected_page': 1, 'pushed': 0, 'done': [], 'errors': []}
        done = set(run['done'])
        settings = {'delay': float(actor_input.get('delaySeconds') or 0.75),
                    'max': int(actor_input.get('maxBreeders') or 0)}

        async def persist(*_):
            run['done'] = list(done)
            await Actor.set_value('STATE', run)

        Actor.on(Event.PERSIST_STATE, persist)
        async with AsyncSession() as session:
            try:
                while run['next_url']:
                    await Actor.set_status_message('%s: page %d (%d breeders so far)' % (
                        run['states'][run['state_index']], run['expected_page'], run['pushed']))
                    keep_going = await import_page(session, run, done, settings)
                    await persist()
                    if not keep_going:
                        await Actor.exit(status_message='Reached maxBreeders (%d).' % settings['max'])
                        return
            except Exception as e:
                if run['errors']:
                    run.update(run['retry_from'], errors=[])
                await persist()
                await Actor.fail(status_message='Stopped: %s' % e)
                return
        for failed in run['errors']:
            await Actor.push_data(failed)
            done.add(failed['Breeder ID'])
            run['pushed'] += 1
        run['errors'] = []
        await persist()
        await Actor.exit(status_message='Complete: %d breeders from %s' % (run['pushed'], ', '.join(run['states'])))
