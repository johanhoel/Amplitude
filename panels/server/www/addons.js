/* Hide the parts of a page this house does not have.
 *
 * Mark an element with data-addon="bus" and it disappears where no bus stop
 * is set. Several names means "any of these": data-addon="pc speakers".
 *
 * The rule lives in wall.css so it applies before this script runs; all this
 * does is put the list of enabled addons on <html>. The last answer is kept
 * in localStorage and applied synchronously on the next load, so a panel that
 * has shown a page before does not flash the controls it is about to hide.
 * A panel that has not is one frame late, which is the right way round: show
 * something and remove it, rather than hide everything and wait.
 */
(function () {
  var KEY = 'homedeck-addons';
  var root = document.documentElement;

  function apply(list) {
    if (typeof list !== 'string') return;
    root.setAttribute('data-addons', list);
  }

  /* For a page that builds its cards in JS rather than marking up every one.
   * Same rule as the stylesheet, including the safe direction: before any
   * answer has arrived nothing is hidden, because showing a card the house
   * has no hardware for is a smaller fault than an empty page. */
  window.hasAddon = function (name) {
    var list = root.getAttribute('data-addons');
    return list === null || list.split(' ').indexOf(name) !== -1;
  };

  try { apply(localStorage.getItem(KEY)); } catch (e) { /* private window */ }

  fetch('/api/addons', { cache: 'no-store' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (d) {
      if (!d || typeof d.enabled !== 'string') return;
      apply(d.enabled);
      try { localStorage.setItem(KEY, d.enabled); } catch (e) { /* ignore */ }
    })
    .catch(function () {
      // No answer: leave whatever the cache had. Hiding the whole page
      // because one request failed would be worse than showing too much.
    });
})();
