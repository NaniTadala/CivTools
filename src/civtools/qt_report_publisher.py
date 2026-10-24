"""Folder-to-report workspace with real PDF previews and sheet-level overrides."""
from pathlib import Path
import json
import threading
import uuid

from PySide6.QtCore import Qt, QTimer, QUrl, QEvent
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QWidget, QLineEdit, QTreeWidgetItem, QFileDialog,
    QInputDialog, QListWidgetItem)
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon

from .jobs import Job
from .core.report_models import discover, resolve_settings, fingerprint
from .core.report_service import ExcelSession, prepare_report, publish


class ReportPublisherPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.busy = False
        self.records = {}
        self.batch = resolve_settings()
        self.template_rules = []
        self.prepared = {}
        self.sheet_cache = {}
        self.preparing = False
        self.passwords = {}
        self.jobs = set()
        self.history = []
        self.preview_serial = 0
        self.preview_path = ''
        self.combined_preview = None
        self.assembly_serial = 0
        self.assembling_signature = None
        self.stop = threading.Event()
        self.stop_now = threading.Event()
        self.setAcceptDrops(True)
        from .qt_pages import config_root
        self.session = config_root() / 'report-jobs' / uuid.uuid4().hex
        self.session.mkdir(parents=True, exist_ok=True)
        from .qt_report_workspace import build_workspace
        build_workspace(self)
        self.set_editor(self.batch)
        self.set_busy(False)

    def restore_state(self, key):
        try:
            state = json.loads(str(self.window.settings.value('reports/state', '{}')))
            self.batch = resolve_settings(state.get('batch'))
            self.output.setText(state.get('output', ''))
            self.recursive.setChecked(state.get('recursive', True))
            self.template_rules = state.get('templates',[])
            export_options = state.get('export',{})
            for name in ('combined','contents','numbering','per_sheet','reviewed'):
                getattr(self,name).setChecked(bool(export_options.get(name,False)))
            self.cover.setText(export_options.get('cover',''))
            self.presets = json.loads(str(self.window.settings.value('reports/presets', '{}')))
        except (ValueError, TypeError):
            self.presets = {}
        for name in self.presets:
            self.preset.addItem(name)
        self.set_editor(self.batch)
        manifest = self.window.settings.value('reports/last_manifest', '')
        if manifest and Path(str(manifest)).is_file():
            try:
                state = json.loads(Path(str(manifest)).read_text(encoding='utf-8'))
                self.records = state['records']
                self.prepared = {k:v for k,v in state.get('prepared',{}).items() if Path(v['artifact']).is_file()}
                self.sheet_cache = {k:v for k,v in state.get('sheet_cache',{}).items() if Path(v['artifact']).is_file()}
                for source, record in self.records.items():
                    if source not in self.prepared and record.get('status') in ('Ready','Needs review'):
                        record['status'] = 'Not prepared'
                self.rebuild()
            except (OSError, ValueError, KeyError):
                pass

    def save_state(self):
        self.window.settings.setValue('reports/state', json.dumps(dict(batch=self.batch, output=self.output.text(), recursive=self.recursive.isChecked(),templates=self.template_rules,
            export={**{name:getattr(self,name).isChecked() for name in ('combined','contents','numbering','per_sheet','reviewed')},'cover':self.cover.text()})))
        manifest = self.session / 'session.json'
        stage = manifest.with_suffix('.tmp')
        stage.write_text(json.dumps(dict(records=self.records, prepared=self.prepared, sheet_cache=self.sheet_cache), indent=2), encoding='utf-8')
        stage.replace(manifest)
        self.window.settings.setValue('reports/last_manifest', str(manifest))

    def set_busy(self, value):
        self.busy = value
        for widget in (self.input_bar,self.editor,self.prepare_button,self.quick_button,self.export_button,self.retry_button,self.output,self.combined_preview_button):
            widget.setEnabled(not value)
        self.update_tree_interaction()
        self.stop_button.setEnabled(value)
        self.stop_button.setVisible(value)
        self.progress.setVisible(value)
        self.kill_button.setEnabled(value)
        self.prepare_button.setEnabled(not value and bool(self.records))
        self.export_button.setEnabled(not value and bool(self.prepared))
        self.clear_button.setEnabled(not value and bool(self.records))
        if value:
            self.stop.clear()
            self.stop_now.clear()
        elif self.records and self.combined.isChecked():
            self.combined_timer.start()
        self.window.update_status()

    def update_tree_interaction(self):
        """Keep browsing available while preventing changes to an active batch."""
        self.tree.setDragEnabled(not self.busy)
        blocked = self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for item in [top]+[top.child(j) for j in range(top.childCount())]:
                flags = item.flags()
                item.setFlags(flags & ~Qt.ItemFlag.ItemIsUserCheckable if self.busy else flags | Qt.ItemFlag.ItemIsUserCheckable)
        self.tree.blockSignals(blocked)

    def run_job(self, operation, success, busy=True):
        if busy:
            self.set_busy(True)
        job = Job(operation)
        self.jobs.add(job)
        job.signals.event.connect(self.job_event)
        job.signals.succeeded.connect(success)
        job.signals.failed.connect(lambda error: self.feedback.setText(error))
        def finished():
            self.jobs.discard(job)
            if busy:
                self.preparing = False
                self.set_busy(False)
                self.save_state()
        job.signals.finished.connect(finished)
        self.window.pool.start(job)

    def job_event(self, kind, value):
        if kind == 'stage':
            self.feedback.setText(str(value))
        elif kind == 'progress':
            self.progress.setValue(value)
        elif kind == 'report_item':
            self.records[value['source']] = value
            self.prepared.pop(value['source'],None)
            self.sheet_cache.pop(value['source'],None)
            self.rebuild()
        elif kind == 'report_prepared':
            record, result = value
            source = record['source']
            previous = self.prepared.pop(source,None)
            self.records[source] = record
            if result:
                self.prepared[source] = result
                self.sheet_cache.pop(source,None)
            elif previous:
                self.sheet_cache[source] = previous
            if not previous or not result or previous['artifact'] != result['artifact']:
                self.reviewed.setChecked(False)
                self.assembly_serial += 1
            self.rebuild(refresh_preview=False)
            current = self.tree.currentItem()
            if result and (not self.preview_path or current and self.key(current)[0]==source):
                if not current or self.key(current)[0] not in self.prepared:
                    current = next(self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount()) if self.key(self.tree.topLevelItem(i))[0]==source)
                    self.tree.setCurrentItem(current)
                key_source,name = self.key(current)
                ready = self.prepared.get(key_source)
                sheet = next((s for s in ready['rendered'] if s['name']==name),None) if ready else None
                path = sheet['path'] if sheet else ready['artifact'] if ready else ''
                if path != self.preview_path:
                    self.selection_changed(current)
            elif not result and current and self.key(current)[0]==source:
                self.selection_changed(current)
            self.save_state()

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Select Excel report folder')
        if path:
            if not self.output.text():
                self.output.setText(str(Path(path) / 'Published PDFs'))
            self.intake([path])

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Select reports', '', 'Excel reports (*.xlsx *.xlsm *.xlsb *.xls)')
        if paths:
            if not self.output.text():
                self.output.setText(str(Path(paths[0]).parent / 'Published PDFs'))
            self.intake(paths)

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, 'Output folder', self.output.text())
        if path:
            self.output.setText(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy:
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.busy:
            return
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            if not self.output.text():
                path = Path(paths[0])
                self.output.setText(str((path if path.is_dir() else path.parent) / 'Published PDFs'))
            self.intake(paths)

    def intake(self, paths):
        recursive, excluded = self.recursive.isChecked(), [self.output.text()]
        rules = list(self.template_rules)
        def operation(report):
            files, ignored = discover(paths, recursive, excluded)
            result = []
            with ExcelSession(report,self.stop_now) as excel:
                for index, item in enumerate(files):
                    if self.stop.is_set() or self.stop_now.is_set():
                        break
                    report('stage', f"Inspecting {index+1}/{len(files)}: {Path(item['source']).name}")
                    try:
                        inventory = excel.call(dict(operation='inspect', source=item['source']))
                        item.update(inventory)
                        item.update(status='Not prepared', overrides={}, included=True)
                        for sheet in item['sheets']:
                            sheet.update(included=sheet['visible'] and not sheet['empty'], overrides={})
                            rule = next((r for r in rules if r['name']==sheet['name'] and r.get('signature') and r['signature']==sheet.get('signature')),None)
                            if rule:
                                sheet['overrides'] = rule['settings']
                    except Exception as error:
                        item.update(status='Failed', error=str(error), sheets=[], overrides={}, included=True)
                    result.append(item)
                    report('report_item',item)
                    report('progress', int((index+1)*100/max(1,len(files))))
            return result, len(ignored)
        def done(result):
            records, ignored = result
            for record in records:
                self.records[record['source']] = record
                self.prepared.pop(record['source'],None)
            self.rebuild()
            self.feedback.setText(f'{len(self.records)} reports added'+(f' · {ignored} skipped' if ignored else ''))
        self.run_job(operation, done)

    def rebuild(self, refresh_preview=True):
        previous = self.key(self.tree.currentItem())
        selection = {tuple(self.key(item)) for item in self.tree.selectedItems()}
        expanded = {self.key(self.tree.topLevelItem(i))[0]:self.tree.topLevelItem(i).isExpanded() for i in range(self.tree.topLevelItemCount())}
        scroll = self.tree.verticalScrollBar().value()
        self.tree.blockSignals(True)
        self.tree.clear()
        for source, record in self.records.items():
            display_status = {'Not prepared':'Queued','Needs review':'Review'}.get(record['status'],record['status'])
            top = QTreeWidgetItem([Path(record['relative']).name, ''])
            top.setData(0, Qt.ItemDataRole.UserRole, (source, ''))
            states = [s['included'] for s in record['sheets']]
            state = (Qt.CheckState.PartiallyChecked if states and not all(states) else Qt.CheckState.Checked) if record.get('included',True) else Qt.CheckState.Unchecked
            top.setCheckState(0,state)
            top.setToolTip(0, source)
            top.setToolTip(1, record.get('error','') or display_status)
            from .qt_report_workspace import status_icon
            top.setIcon(1,status_icon({'Ready':'#258568','Failed':'#BC5555','Needs review':'#B78030'}.get(record['status'],'#8A9CA8')))
            self.tree.addTopLevelItem(top)
            for sheet in record['sheets']:
                status = 'Hidden' if not sheet['visible'] else 'Empty' if sheet['empty'] else ''
                child = QTreeWidgetItem([sheet['name'], status])
                child.setData(0, Qt.ItemDataRole.UserRole, (source,sheet['name']))
                child.setToolTip(0,sheet['name'])
                child.setCheckState(0, Qt.CheckState.Checked if sheet['included'] else Qt.CheckState.Unchecked)
                top.addChild(child)
            top.setExpanded(expanded.get(source,len(self.records)<5))
        self.update_tree_interaction()
        self.filter_tree()
        self.report_count.setText(f'{len(self.records)} reports' if self.records else 'No reports yet')
        self.report_sidebar.setVisible(bool(self.records))
        self.clear_button.setVisible(bool(self.records))
        self.clear_button.setEnabled(not self.busy and bool(self.records))
        self.filter.setVisible(len(self.records)>1)
        self.prepare_button.setEnabled(not self.busy and bool(self.records))
        self.export_button.setEnabled(not self.busy and bool(self.prepared))
        if not self.busy:
            counts = [(sum(r['status']==status for r in self.records.values()),label) for status,label in
                      [('Ready','ready'),('Needs review','to review'),('Failed','failed'),('Not prepared','queued')]]
            self.feedback.setText(' · '.join(f'{n} {label}' for n,label in counts if n) or 'Add reports to begin')
        selected = None
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for item in [top]+[top.child(j) for j in range(top.childCount())]:
                if self.key(item)==previous:
                    selected = item
        if selected is not None:
            self.tree.setCurrentItem(selected)
        elif self.tree.topLevelItemCount() and self.prepared:
            selected = next((self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount()) if self.key(self.tree.topLevelItem(i))[0] in self.prepared),None)
            self.tree.setCurrentItem(selected)
        if selection:
            for i in range(self.tree.topLevelItemCount()):
                top = self.tree.topLevelItem(i)
                for item in [top]+[top.child(j) for j in range(top.childCount())]:
                    item.setSelected(tuple(self.key(item)) in selection)
        self.tree.verticalScrollBar().setValue(scroll)
        self.tree.blockSignals(False)
        if not self.records:
            self.show_empty_workspace()
        elif refresh_preview and selected:
            self.selection_changed(selected)

    def clear_preview(self):
        """Discard displayed documents and invalidate callbacks still in flight."""
        self.preview_serial += 1
        self.assembly_serial += 1
        self.preview_path = ''
        self.combined_preview = None
        self.assembling_signature = None
        self.combined_timer.stop()
        self.preview_resize_timer.stop()
        self.thumbnail_timer.stop()
        self.thumbnail_path = ''
        self.thumbnail_pending.clear()
        self.thumbnails.clear()
        self.preview.setText('')
        self.preview_name.setText('Preview')
        self.page.set_page_count(1)
        self.page.blockSignals(True)
        self.page.setValue(1)
        self.page.blockSignals(False)
        self.page_total.setText('/ 1')
        self.reason.clear()
        self.details_button.hide()

    def show_empty_workspace(self):
        self.prepared.clear()
        self.sheet_cache.clear()
        self.passwords.clear()
        self.history.clear()
        self.clear_preview()
        self.search.clear()
        self.filter.setCurrentIndex(0)
        self.scope.setText('All reports')
        self.set_editor(self.batch)
        self.progress.setValue(0)
        self.feedback.setText('Add reports to begin')

    def key(self, item):
        return item.data(0,Qt.ItemDataRole.UserRole) if item else None

    def sheet_record(self, source, name):
        return next(s for s in self.records[source]['sheets'] if s['name']==name)

    def effective(self, source, name=''):
        return resolve_settings(self.batch, self.records[source]['overrides'], self.sheet_record(source,name)['overrides'] if name else None)

    def filter_tree(self, *args):
        query, status = self.search.text().casefold(), self.filter.currentText()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            record = self.records[self.key(top)[0]]
            match = query in (record['source']+' '+' '.join(s['name'] for s in record['sheets'])).casefold()
            top.setHidden(not match or (status!='All reports' and record['status'] != status))

    def inclusion_changed(self, item, column):
        if column != 0 or self.busy:
            return
        source, name = self.key(item)
        included = item.checkState(0)==Qt.CheckState.Checked
        record = self.records[source]
        if name:
            self.sheet_record(source,name)['included'] = included
            record['included'] = any(s['included'] for s in record['sheets'])
        else:
            record['included'] = included
            for sheet in record['sheets']:
                sheet['included'] = included
        # Keep the emitting item alive until Qt has finished the checkbox event.
        top = item.parent() if name else item
        self.tree.blockSignals(True)
        try:
            states = [s['included'] for s in record['sheets']]
            state = (Qt.CheckState.PartiallyChecked if states and not all(states) else Qt.CheckState.Checked) if record['included'] else Qt.CheckState.Unchecked
            top.setCheckState(0,state)
            for i,sheet in enumerate(record['sheets']):
                top.child(i).setCheckState(0,Qt.CheckState.Checked if sheet['included'] else Qt.CheckState.Unchecked)
        finally:
            self.tree.blockSignals(False)
        self.reassemble_workbook(source)
        self.schedule_combined_preview()
        self.save_state()

    def invalidate(self, source):
        previous = self.prepared.pop(source,None)
        if previous:
            self.sheet_cache[source] = previous
        self.records[source]['status'] = 'Not prepared'
        self.reviewed.setChecked(False)
        self.schedule_combined_preview()
        if self.preview_path:
            self.preview_serial += 1
            self.preview_path = ''
            self.preview.clear()
            self.preview.setText('Settings changed. Prepare again to see the updated PDF.')

    def selection_changed(self, item, previous=None):
        key = self.key(item)
        if not key:
            return
        source, name = key
        self.scope.setText(name or Path(source).name)
        self.set_editor(self.effective(source,name))
        if self.combined.isChecked() and not self.busy and len(self.assembly_selection()[0])==len(self.assembly_selection()[1]):
            self.combined_timer.start()
            return
        prepared = self.prepared.get(source)
        record = self.records[source]
        self.reason.setText(record.get('error','') or '\n'.join(record.get('issues',[])))
        if prepared:
            sheet = next((s for s in prepared['rendered'] if s['name']==name),None)
            self.reason.setText('\n'.join(prepared['issues']))
            if sheet:
                self.reason.setText(sheet['plan']['reason']+'\n'+'\n'.join(sheet['issues']))
            self.preview_path = sheet['path'] if sheet else prepared['artifact']
            self.preview_name.setText((name or Path(source).name)+(' · individual preview' if self.combined.isChecked() else ''))
            self.preview_name.setToolTip(name or Path(source).name)
            self.page.blockSignals(True)
            self.page.setValue(1)
            self.page.blockSignals(False)
            self.render_preview()
        else:
            self.preview_serial += 1
            self.preview_path = ''
            self.preview.clear()
            self.preview.setText('Prepare this workbook to preview its report.')
        self.details_button.setVisible(bool(self.reason.text()))

    def set_editor(self, settings):
        self.orientation.setCurrentText(settings['orientation'])
        self.paper.setCurrentText(settings['paper'])
        self.a3.setChecked(settings['allow_a3'])
        self.font.setValue(settings['minimum_font'])
        self.margin.setValue(settings['margin_mm'])
        self.area_mode.setCurrentText(settings['area_mode'])
        self.area.setText(settings['print_area'])
        self.titles.setText(settings['title_rows'])
        self.repair.setChecked(settings['repair_tables'])
        self.recalculate.setChecked(settings['recalculate'])
        self.breaks.setText(settings['section_breaks'])
        self.keep_sections.setChecked(settings['keep_sections'])
        self.repeat_headings.setChecked(settings['repeat_headings'])

    def editor_settings(self):
        return resolve_settings(dict(orientation=self.orientation.currentText(),paper=self.paper.currentText(),allow_a3=self.a3.isChecked(),
            minimum_font=self.font.value(),margin_mm=self.margin.value(),area_mode=self.area_mode.currentText(),print_area=self.area.text().strip(),
            title_rows=self.titles.text().strip(),repair_tables=self.repair.isChecked(),recalculate=self.recalculate.isChecked(),section_breaks=self.breaks.text().strip(),
            keep_sections=self.keep_sections.isChecked(),repeat_headings=self.repeat_headings.isChecked()))

    def apply_selected(self):
        if self.busy:
            return
        try:
            settings = self.editor_settings()
            self.remember_layout()
            for item in self.tree.selectedItems():
                source,name = self.key(item)
                target = self.sheet_record(source,name) if name else self.records[source]
                parent = self.effective(source) if name else self.batch
                target['overrides'] = {k:v for k,v in settings.items() if v != parent[k]}
                self.invalidate(source)
            self.rebuild()
            self.feedback.setText('Layout updated · prepare to refresh')
        except ValueError as error:
            self.feedback.setText(str(error))

    def reset_selected(self):
        if self.busy:
            return
        self.remember_layout()
        for item in self.tree.selectedItems():
            source,name = self.key(item)
            (self.sheet_record(source,name) if name else self.records[source])['overrides'] = {}
            self.invalidate(source)
        self.rebuild()

    def apply_batch(self):
        if self.busy:
            return
        try:
            self.remember_layout()
            self.batch = self.editor_settings()
            for source in self.records:
                self.invalidate(source)
            self.rebuild()
            self.save_state()
        except ValueError as error:
            self.feedback.setText(str(error))

    def remember_layout(self):
        self.history.append(json.loads(json.dumps(dict(batch=self.batch,records=self.records))))
        self.history = self.history[-20:]

    def undo_layout(self):
        if self.busy or not self.history:
            return
        state = self.history.pop()
        self.batch, self.records = state['batch'],state['records']
        for source in self.records:
            self.invalidate(source)
        self.set_editor(self.batch)
        self.rebuild()
        self.feedback.setText('Previous layout settings restored. Prepare reports to update PDFs.')

    def save_preset(self):
        name, accepted = QInputDialog.getText(self, 'Save publishing preset', 'Preset name')
        if accepted and name.strip():
            try:
                rules = []
                for source,record in self.records.items():
                    for sheet in record['sheets']:
                        if sheet.get('signature') and sheet.get('included'):
                            rules.append(dict(name=sheet['name'],signature=sheet['signature'],settings=self.effective(source,sheet['name'])))
                self.presets[name.strip()] = dict(batch=self.editor_settings(),templates=rules)
                self.window.settings.setValue('reports/presets',json.dumps(self.presets))
                if self.preset.findText(name.strip())<0:
                    self.preset.addItem(name.strip())
                self.preset.setCurrentText(name.strip())
            except ValueError as error:
                self.feedback.setText(str(error))

    def load_preset(self, name):
        if self.busy:
            return
        preset = getattr(self,'presets',{}).get(name,{})
        self.batch = resolve_settings(preset.get('batch',preset))
        self.template_rules = preset.get('templates',[])
        self.set_editor(self.batch)
        for source in self.records:
            self.invalidate(source)
        self.rebuild()

    def set_password(self):
        key = self.key(self.tree.currentItem())
        if not key:
            return
        value, ok = QInputDialog.getText(self,'Workbook password','Password for this session',QLineEdit.EchoMode.Password)
        if ok:
            self.passwords[key[0]] = value
            self.feedback.setText('Password stored for this session. Prepare reports to retry.')

    def move_item(self, delta):
        item = self.tree.currentItem()
        if item is None or self.busy:
            return
        source,name = self.key(item)
        if name:
            sheets = self.records[source]['sheets']
            index = next(i for i,s in enumerate(sheets) if s['name']==name)
            self.reorder_item(source,name,index+delta)
        else:
            keys = list(self.records)
            index = keys.index(source)
            self.reorder_item(source,name,index+delta)

    def reorder_item(self,source,name,index):
        if self.busy:
            return
        if name:
            sequence = self.records[source]['sheets']
            old = next(i for i,s in enumerate(sequence) if s['name']==name)
        else:
            sequence = list(self.records)
            old = sequence.index(source)
        if not 0<=index<len(sequence) or old==index:
            return
        sequence.insert(index,sequence.pop(old))
        if not name:
            self.records = {key:self.records[key] for key in sequence}
        self.schedule_combined_preview()
        self.rebuild()
        if name:
            self.reassemble_workbook(source)
        self.save_state()

    def reassemble_workbook(self,source):
        """Reorder/exclude cached sheet PDFs without another Excel conversion."""
        prepared = self.prepared.get(source)
        selected = [s['name'] for s in self.records[source]['sheets'] if s['included'] and not s['empty']]
        available = prepared.get('available_rendered',prepared.get('rendered',[])) if prepared else []
        by_name = {s['name']:s for s in available}
        if not selected:
            # Keep the cached sheet PDFs so checking the workbook again can
            # restore it without another Excel conversion.
            self.schedule_combined_preview()
            return
        if not set(selected)<=set(by_name):
            self.invalidate(source)
            QTimer.singleShot(0,self.rebuild)
            return
        snapshot = dict(prepared)
        available_settings = snapshot.get('available_settings',snapshot.get('settings',{}))
        rendered = [by_name[name] for name in selected]
        output = self.session/(uuid.uuid4().hex+'.pdf')
        def operation(report):
            if fingerprint(source)!=snapshot['fingerprint']:
                raise ValueError('Source workbook changed. Prepare it again.')
            mapping = self.window.pdf.call('report',report,'assemble',dict(entries=[dict(name=s['name'],path=s['path']) for s in rendered],output=str(output)))
            global_issues = snapshot.get('workbook_issues',[issue for issue in snapshot['issues'] if not any(issue.startswith(s['name']+': ') for s in available)])
            issues = list(global_issues)+[f"{s['name']}: {issue}" for s in rendered for issue in s['issues']]
            return dict(snapshot,artifact=str(output),rendered=rendered,available_rendered=available,page_map=mapping,issues=issues,workbook_issues=global_issues,
                settings={name:available_settings.get(name) for name in selected},available_settings=available_settings)
        self.prepared.pop(source,None)
        self.records[source]['status'] = 'Not prepared'
        def done(result):
            self.prepared[source] = result
            self.records[source]['status'] = 'Needs review' if result['issues'] else 'Ready'
            self.rebuild()
            self.schedule_combined_preview()
        self.run_job(operation,done)

    def remove_selected(self):
        if self.busy:
            return
        self.remove_reports({self.key(i)[0] for i in self.tree.selectedItems()})

    def remove_all(self):
        self.remove_reports(list(self.records))

    def remove_reports(self, sources):
        if self.busy or not sources:
            return
        for source in sources:
            self.records.pop(source,None)
            self.prepared.pop(source,None)
            self.sheet_cache.pop(source,None)
            self.passwords.pop(source,None)
        self.history.clear()
        self.clear_preview()
        self.rebuild()
        if self.records:
            if self.tree.currentItem() is None:
                self.tree.setCurrentItem(self.tree.topLevelItem(0))
            self.schedule_combined_preview()
        self.save_state()

    def prepare(self, auto_export=False, exceptions_only=False):
        if self.busy:
            return
        snapshot = json.loads(json.dumps(self.records))
        batch = dict(self.batch)
        passwords = dict(self.passwords)
        cached = {**self.sheet_cache,**self.prepared}
        def operation(report):
            selected = [r for r in snapshot.values() if r.get('included',True) and (not exceptions_only or r['status'] in ('Failed','Needs review'))]
            with ExcelSession(report,self.stop_now) as excel:
                for index, record in enumerate(selected):
                    if self.stop.is_set() or self.stop_now.is_set():
                        break
                    source = record['source']
                    try:
                        if not record['sheets']:
                            inventory = excel.call(dict(operation='inspect',source=source,password=passwords.get(source,'')))
                            record.update(inventory)
                            for sheet in record['sheets']:
                                sheet.update(included=sheet['visible'] and not sheet['empty'],overrides={})
                        sheets = {s['name']:resolve_settings(batch,record['overrides'],s['overrides']) for s in record['sheets'] if s['included'] and not s['empty']}
                        if not sheets:
                            raise ValueError('No nonempty sheets selected.')
                        report('stage',f"Preparing {index+1}/{len(selected)}: {Path(source).name}")
                        result = prepare_report(record,sheets,resolve_settings(batch,record['overrides']),
                            self.session/uuid.uuid4().hex,excel,self.window.pdf,report,
                            cached=cached.get(source),password=passwords.get(source,''),force=exceptions_only)
                        record.update(status='Needs review' if result['issues'] else 'Ready',error='')
                    except Exception as error:
                        record.update(status='Failed',error=str(error))
                        result = None
                    # Commit each result before starting the next workbook.
                    report('report_prepared',(record,result))
                    report('progress',int((index+1)*100/max(1,len(selected))))
        def done(unused):
            self.rebuild(refresh_preview=False)
            ready = sum(r['status']=='Ready' for r in self.records.values())
            counts = [(ready,'ready'),(sum(r['status']=='Needs review' for r in self.records.values()),'to review'),
                      (sum(r['status']=='Failed' for r in self.records.values()),'failed')]
            self.feedback.setText(' ? '.join(f'{count} {label}' for count,label in counts if count) or 'No reports prepared')
            if auto_export:
                QTimer.singleShot(100,self.export)
        self.preparing = True
        self.assembly_serial += 1
        self.run_job(operation,done)

    def render_preview(self, *args):
        if not self.preview_path:
            return
        self.preview_serial += 1
        serial = self.preview_serial
        zoom = self.zoom.currentText()
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff if zoom=='Fit width' else Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        payload = dict(path=self.preview_path)
        scale = 1. if zoom=='Fit width' else int(zoom.rstrip('%'))/100
        fit_width = 0
        if zoom=='Fit width':
            fit_width = max(150,self.preview_scroll.viewport().width()-40)
        def done(sizes):
            if serial != self.preview_serial:
                return
            pages = len(sizes)
            self.page.set_page_count(pages)
            self.page_total.setText('/ '+str(pages))
            self.preview.set_document(payload['path'],sizes,scale,fit_width)
            show_thumbnails = pages>1
            if self.thumbnails.isHidden()==show_thumbnails:
                self.thumbnails.setVisible(show_thumbnails)
                self.preview_resize_timer.start()
            if self.thumbnail_path != payload['path']:
                self.thumbnail_path = payload['path']
                self.thumbnails.clear()
                self.thumbnail_pending.clear()
                for index in range(pages):
                    item = QListWidgetItem(str(index+1))
                    item.setData(Qt.ItemDataRole.UserRole,index)
                    item.setSizeHint(QSize(64,108))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
                    self.thumbnails.addItem(item)
                self.request_thumbnails()
        self.run_job(lambda report:self.window.pdf.call('report',report,'page_sizes',payload),done,False)

    def request_thumbnails(self, *args):
        self.thumbnail_timer.start()

    def load_thumbnails(self):
        path = self.thumbnail_path
        visible = [i for i in range(self.thumbnails.count()) if self.thumbnails.visualItemRect(self.thumbnails.item(i)).intersects(self.thumbnails.viewport().rect())]
        for index in visible[:8]:
            item = self.thumbnails.item(index)
            if not item.icon().isNull() or (path,index) in self.thumbnail_pending:
                continue
            self.thumbnail_pending.add((path,index))
            def done(result, index=index, path=path):
                self.thumbnail_pending.discard((path,index))
                if path != self.thumbnail_path:
                    return
                pixmap = QPixmap()
                pixmap.loadFromData(result['image'])
                self.thumbnails.item(index).setIcon(QIcon(pixmap))
                # Keep the thumbnail image cache bounded while retaining page navigation.
                for other in range(self.thumbnails.count()):
                    if abs(other-index)>16:
                        self.thumbnails.item(other).setIcon(QIcon())
            self.run_job(lambda report,index=index:self.window.pdf.call('report',report,'preview',dict(path=path,page=index,zoom=.1)),done,False)

    def open_pdf(self):
        if self.preview_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.preview_path))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'preview_resize_timer'):
            self.preview_resize_timer.start()

    def eventFilter(self,watched,event):
        if (hasattr(self,'preview_resize_timer') and watched is self.preview_scroll.viewport()
                and event.type()==QEvent.Type.Resize):
            self.preview_resize_timer.start()
        return super().eventFilter(watched,event)

    def assembly_selection(self):
        selected = [r for r in self.records.values() if r.get('included',True)]
        ready = [self.prepared[r['source']] for r in selected if r['source'] in self.prepared and (r['status']=='Ready' or self.reviewed.isChecked())]
        options = dict(combined=self.combined.isChecked(),cover=self.cover.text(),contents=self.contents.isChecked(),numbering=self.numbering.isChecked(),per_sheet=self.per_sheet.isChecked())
        signature = json.dumps(dict(sources=[(r['source'],r['fingerprint'],r['artifact']) for r in ready],options=options),sort_keys=True)
        return selected,ready,options,signature

    def schedule_combined_preview(self,*args):
        if not self.records:
            self.show_empty_workspace()
            return
        self.assembly_serial+=1
        if self.preparing:
            return
        self.preview_serial+=1
        if self.combined.isChecked():
            self.preview_path = ''
            self.details_button.hide()
            self.preview.clear()
            self.preview.setText('')
            self.empty_title.setText('Combined report')
            self.empty_copy.setText('Preparing the preview in your report order…')
            self.combined_timer.start()
        else:
            self.combined_timer.stop()
            current = self.tree.currentItem()
            if current:
                self.selection_changed(current)

    def preview_combined(self,automatic=False):
        self.combined_timer.stop()
        if not self.records:
            self.show_empty_workspace()
            return
        if self.busy:
            return
        if not automatic and not self.combined.isChecked():
            self.combined.setChecked(True)
            self.combined_timer.stop()
        if automatic and not self.combined.isChecked():
            return
        selected,ready,options,signature = self.assembly_selection()
        if not ready or len(ready)!=len(selected):
            individual_paths = {p['artifact'] for p in self.prepared.values()}
            individual_paths.update(s['path'] for p in self.prepared.values() for s in p.get('rendered',[]))
            if self.preview_path in individual_paths:
                return
            if self.combined.isChecked():
                self.preview_path = ''
                self.preview.clear()
                self.preview.setText('')
                self.empty_title.setText('Combined report')
                self.empty_copy.setText('Prepare the included reports and review any exceptions.')
            if not automatic:
                self.feedback.setText('Prepare the included reports and review any exceptions.')
            return
        if self.combined_preview and self.combined_preview[0]==signature:
            if self.preview_path!=self.combined_preview[1]:
                self.preview_path=self.combined_preview[1]
                self.preview_name.setText('Combined report')
                self.render_preview()
            return
        if self.assembling_signature==(self.assembly_serial,signature):
            return
        serial=self.assembly_serial
        self.assembling_signature=(serial,signature)
        output = self.session / (uuid.uuid4().hex+'.pdf')
        def operation(report):
            for record in ready:
                if fingerprint(record['source']) != record['fingerprint']:
                    raise ValueError('A source workbook changed. Prepare it again.')
            return self.window.pdf.call('report',report,'assemble',dict(entries=[dict(name=Path(r['relative']).stem,path=r['artifact']) for r in ready],
                output=str(output),cover=options['cover'],contents=options['contents'],numbering=options['numbering']))
        def done(result):
            if self.assembling_signature==(serial,signature):
                self.assembling_signature=None
            if serial!=self.assembly_serial or not self.combined.isChecked() or signature!=self.assembly_selection()[3]:
                return
            self.combined_preview = (signature,str(output))
            self.preview_path = str(output)
            self.preview_name.setText('Combined report')
            self.page.blockSignals(True)
            self.page.setValue(1)
            self.page.blockSignals(False)
            self.render_preview()
            self.reason.setText('Combined report preview. Export uses these exact bytes when the assembly settings are unchanged.')
        self.run_job(operation,done,busy=not automatic)

    def export(self):
        if self.busy:
            return
        if not self.output.text().strip():
            self.feedback.setText('Choose an output folder first.')
            return
        selected,ready,options,signature = self.assembly_selection()
        if not ready:
            self.feedback.setText('Prepare reports first, then review any exceptions.')
            return
        if self.combined.isChecked() and len(ready)!=len(selected):
            self.feedback.setText('Combined report is incomplete. Resolve exceptions or explicitly exclude those workbooks.')
            return
        destination = self.output.text()
        if self.combined_preview and self.combined_preview[0]==signature:
            options['combined_artifact'] = self.combined_preview[1]
        self.run_job(lambda report:publish(ready,destination,self.window.pdf,report,**options),
                     lambda paths:self.feedback.setText(f'{len(paths)} PDFs saved'+(f' · {len(selected)-len(ready)} held for review' if len(selected)>len(ready) else '')))
