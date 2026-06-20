import requests
import json
import os
import datetime
import mimetypes
import time


class SessionExpiredError(Exception):
    """Raised when the validationkey/JSESSIONID are no longer valid."""
    pass

class CloudManager:
    def __init__(self, domain, username=None, password=None, validationkey=None, session_cookie=None, upload_endpoint=None):
        self.domain = domain
        self.username = username
        self.password = password
        # Optional override for the upload endpoint. When not set it is resolved
        # lazily from /sapi/system/information (see _upload_base_url).
        self.upload_endpoint = upload_endpoint
        self._upload_base = None
        self._sysinfo = None
        self._max_upload = None
        self.session = requests.Session()
        # Some endpoints sit behind CloudFront/WAF and reject non-browser clients,
        # so present a browser-like User-Agent for every request.
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        })
        self.base_url = f'https://{self.domain}/'
        if validationkey:
            # Session injection mode: the login endpoint is protected by the
            # provider's WAF/MFA, so reuse a session captured from the browser.
            # The validation key is also a (longer-lived) cookie that the server
            # may rotate; set it so we present a complete session and can follow
            # rotations via the `validationkey` property below.
            self._validationkey = validationkey
            self.session.cookies.set('validationKey', validationkey, domain=self.domain)
            if session_cookie:
                self.session.cookies.set('JSESSIONID', session_cookie, domain=self.domain)
        else:
            self._validationkey = self.login()

    @property
    def validationkey(self):
        # Prefer the (possibly rotated) cookie value so requests stay in sync with
        # the server instead of pinning a stale key.
        return self.session.cookies.get('validationKey') or self._validationkey

    def login(self):
        login_url = self.base_url + "sapi/login"
        params = {'action': 'login'}
        data = {'login': self.username, 'password': self.password}
        headers = {'referer': self.base_url}       
        response = self.session.post(login_url, params=params, data=data, headers=headers)
        user_info = response.json()
        return user_info['data']['validationkey']
    
    def _json(self, response):
        # Parse a JSON response, turning the "HTML login page" returned for an
        # expired session into a clear SessionExpiredError instead of a confusing
        # JSONDecodeError deep in the call stack.
        try:
            return response.json()
        except ValueError:
            raise SessionExpiredError(
                "Sesión inválida o caducada (HTTP %s). Refresca VALIDATION_KEY y "
                "SESSION_COOKIE desde el navegador." % response.status_code
            )

    def check_session(self):
        # Lightweight validity check performed up front.
        url = self.base_url + 'sapi/media/folder'
        response = self.session.post(url, params={'action': 'get', 'limit': 1, 'validationkey': self.validationkey})
        data = self._json(response)
        if response.status_code != 200 or not isinstance(data, dict) or 'data' not in data:
            raise SessionExpiredError(
                "Sesión inválida o caducada (HTTP %s). Refresca VALIDATION_KEY y "
                "SESSION_COOKIE desde el navegador." % response.status_code
            )
        return True

    def get_file_info(self,file_id):
        get_file_info_url = self.base_url + 'sapi/media'
        params = {'action':'get','validationkey': self.validationkey}
        json_data = {'data':{'ids':[file_id]}}
        response = self.session.post(get_file_info_url,params=params,json=json_data)
        file_info = response.json()
        return file_info

    def get_root_folder_id(self):
        get_root_folder_id_url = self.base_url + 'sapi/media/folder'
        params = {'action': 'get','limit':1,'validationkey': self.validationkey}
        response = self.session.post(get_root_folder_id_url, params=params)
        root_folders_info = self._json(response)
        root_folder_id = root_folders_info['data']['folders'][0]['id']
        return root_folder_id

    def list_folders(self, parentid, previous_folders=False):
        # Iterative pagination (was recursive, which overflowed the stack and even
        # looped forever when a folder had an exact multiple of 200 subfolders).
        list_subfolders_url = self.base_url + 'sapi/media/folder'
        limit = 200
        all_folders = []
        while True:
            params = {'action': 'list', 'parentid': parentid, 'limit': limit, 'validationkey': self.validationkey}
            if all_folders:
                params['offset'] = len(all_folders)
            response = self.session.get(list_subfolders_url, params=params)
            page = self._json(response)['data']['folders']
            all_folders.extend(page)
            if len(page) < limit:
                return all_folders

    def list_files(self, folderid, previous_files=False):
        # Iterative pagination using the server's "more" flag (was recursive).
        list_folder_files_url = self.base_url + 'sapi/media'
        json_data = {"data": {"fields": ["name", "modificationdate", "size"]}}
        all_files = []
        while True:
            params = {'action': 'get', 'folderid': folderid, 'limit': 200, 'validationkey': self.validationkey}
            if all_files:
                params['offset'] = len(all_files)
            response = self.session.post(list_folder_files_url, params=params, json=json_data)
            data = self._json(response)['data']
            all_files.extend(data['media'])
            if not data.get('more'):
                return all_files
    
    def move_uncategorized_timeline(self,folder_id):
        get_timeline_ids_url = self.base_url + 'sapi/media/timeline'
        params = {'action':'get','validationkey':self.validationkey}
        json_data = {"data":{"source":"media","types":["picture","video"],"sortorder":"uploaded","origin":["omh"]}}
        response = self.session.post(get_timeline_ids_url, params=params,json=json_data)
        file_ids_data = self._json(response)
        #file_ids = file_ids_data['data']['periods'][0]['ids']
        if len(file_ids_data['data']['periods']) > 0:
            for period in file_ids_data['data']['periods']:
                for file_id in period['ids']:
                    self.move_file(file_id,folder_id)
        
    
    def list_all(self,parentid):
        items=[]
        def walk(folderid,current_path):
            subfolders=self.list_folders(folderid)
            subfolders=sorted(subfolders,key=lambda x:x['name'])
            for folder in subfolders:
                if current_path=="":
                    p="\\"+folder['name']
                else:
                    p=current_path+"\\"+folder['name']
                obj={'id':folder['id'],'name':folder['name'],'path':p,'kind':'folder'}
                items.append(obj)
                walk(folder['id'],p)
            folder_files=self.list_files(folderid)
            folder_files=sorted(folder_files,key=lambda x:x['name'])
            for f in folder_files:
                if current_path=="":
                    p="\\"+f['name']
                else:
                    p=current_path+"\\"+f['name']
                obj={'id':f['id'],'name':f['name'],'path':p,'kind':'file'}
                items.append(obj)
        walk(parentid,"")
        return items

    def create_folder(self,name,parentid=False):
        if parentid == False:
            parentid = self.get_root_folder_id()
        create_folder_url = self.base_url + 'sapi/media/folder'
        params = {'action':'save','validationkey':self.validationkey}
        json_data = {"data":{"magic":False,"offline":False,"name":name,"parentid":parentid}}
        response = self.session.post(create_folder_url,json=json_data,params=params)

    def _system_info(self):
        # Cached /sapi/system/information (used for upload endpoint and limits).
        if self._sysinfo is None:
            try:
                response = self.session.get(self.base_url + 'sapi/system/information', params={'action': 'get'})
                self._sysinfo = response.json()
            except Exception:
                self._sysinfo = {}
        return self._sysinfo

    def _upload_base_url(self):
        # Resolve the upload endpoint. Some providers (e.g. O2) serve uploads from a
        # dedicated host (sapi.upload.endpoint) instead of the main domain.
        if self._upload_base:
            return self._upload_base
        base = self.upload_endpoint
        if not base:
            info = self._system_info()
            base = info.get('sapi.client.web.upload.endpoint') or info.get('sapi.upload.endpoint')
        if not base:
            base = self.base_url.rstrip('/')
        self._upload_base = base.rstrip('/')
        return self._upload_base

    def _max_upload_bytes(self):
        # Per-file upload size limit advertised by the server (default 4096 MB).
        if self._max_upload is None:
            mb = self._system_info().get('sapi.upload.max-size-in-mb')
            try:
                mb = int(mb)
            except (TypeError, ValueError):
                mb = 4096
            self._max_upload = mb * 1024 * 1024
        return self._max_upload

    def upload_file(self, file_path, folder_id, retries=3):
        upload_url = self._upload_base_url() + '/sapi/upload'
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        mod_time = os.path.getmtime(file_path)
        mod_date = datetime.datetime.fromtimestamp(mod_time)
        formatted_date = mod_date.strftime("%Y%m%dT%H%M%SZ")
        content_type = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
        metadata = {"data":{"name":file_name,"size":file_size,"modificationdate":formatted_date,"contenttype":content_type,"folderid":folder_id}}
        params = {'action': 'save','acceptasynchronous': 'true','validationkey': self.validationkey,}
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                with open(file_path, 'rb') as file:
                    files = {
                        'data': (None, json.dumps(metadata), 'application/json'),
                        'file': (file_name, file, content_type)
                    }
                    response = self.session.post(upload_url, params=params, files=files, timeout=(30, 600))
                # An expired session returns the HTML login page instead of JSON.
                if response.status_code in (401, 403):
                    raise SessionExpiredError(
                        "Sesión inválida o caducada (HTTP %s). Refresca VALIDATION_KEY y "
                        "SESSION_COOKIE desde el navegador." % response.status_code)
                try:
                    data = response.json()
                except ValueError:
                    raise SessionExpiredError(
                        "Respuesta no-JSON del servidor al subir (probable sesión caducada). "
                        "Refresca VALIDATION_KEY y SESSION_COOKIE.")
                if isinstance(data, dict) and ('success' in data or data.get('id')):
                    return data
                last_error = data.get('error', data) if isinstance(data, dict) else data
            except SessionExpiredError:
                raise
            except requests.RequestException as e:
                last_error = e
            if attempt < retries:
                time.sleep(2 ** attempt)  # backoff: 2s, 4s, ...
        raise RuntimeError("No se pudo subir %s tras %d intentos: %s" % (file_name, retries, last_error))
    
    def download_file(self, fileid, save_path=None):
        if save_path is None:
            save_path = os.getcwd()
        file_info_url = self.base_url + 'sapi/media'
        params = {'action': 'get', 'origin': 'omh,dropbox', 'validationkey': self.validationkey}
        json_data = {"data": {"ids": [fileid], "fields": ["url", "name"]}}
        response = self.session.post(file_info_url, params=params, json=json_data)
        file_info = response.json()
        download_url = file_info['data']['media'][0]['url']
        name = file_info['data']['media'][0]['name']
        file_path = os.path.join(save_path, name)
        
        response = self.session.get(download_url, stream=True)
        with open(file_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    file.write(chunk)
        
        return file_path
    
    def move_file(self,file_id,folder_id):
        move_file_url = self.base_url + 'sapi/media/folder'
        params = {'action':'add-item','validationkey':self.validationkey}
        json_data = {'data':{'items':[file_id],'folderid':folder_id}}
        response = self.session.post(move_file_url, params=params, json=json_data)

    def remove_file(self,file_id,softdelete):
        file_info = self.get_file_info(file_id)
        mediatype = file_info['data']['media'][0]['mediatype']
        plural = mediatype + 's'
        remove_file_url = self.base_url + 'sapi/media/' + mediatype
        params = {'action':'delete','softdelete':softdelete,'validationkey':self.validationkey}
        json_data = {'data':{plural:[file_id]}}
        self.session.post(remove_file_url,json=json_data,params=params)
    
    def remove_folder(self,folder_id,softdelete):
        # The server expects action=delete with a softdelete flag (same shape as
        # remove_file); action=softdelete returns "Missing required parameter".
        remove_folder_url = self.base_url + 'sapi/media/folder'
        params = {'action':'delete','softdelete':softdelete,'validationkey': self.validationkey}
        json_data = {'data':{'folders':[folder_id]}}
        self.session.post(remove_folder_url,json=json_data,params=params)

    def get_free_space_kb(self):
        quota_stats_url = self.base_url + "sapi/media"
        params = {'action':'get-storage-space','softdeleted':True,'validationkey': self.validationkey}
        response = self.session.get(quota_stats_url, params=params)
        quota_stats = response.json()
        free_space_kb = quota_stats['data']['free'] - quota_stats['data']['softdeleted']
        return free_space_kb
        
    def sync_local_path(self,local_path,parentid=False):
        if parentid==False:
            parentid=self.get_root_folder_id()
        local_path=os.path.abspath(local_path)
        def sync_folder(path,folderid):
            entries=os.listdir(path)
            local_dirs=[e for e in entries if os.path.isdir(os.path.join(path,e))]
            local_files=[e for e in entries if os.path.isfile(os.path.join(path,e))]
            remote_folders=self.list_folders(folderid)
            remote_files=self.list_files(folderid)
            remote_folder_map={f['name']:f for f in remote_folders}
            remote_file_map={f['name']:f for f in remote_files}
            for d in local_dirs:
                if d in remote_folder_map:
                    child_id=remote_folder_map[d]['id']
                else:
                    self.create_folder(d,folderid)
                    remote_folders=self.list_folders(folderid)
                    remote_folder_map={f['name']:f for f in remote_folders}
                    child_id=remote_folder_map[d]['id']
                sync_folder(os.path.join(path,d),child_id)
            for fname in local_files:
                full=os.path.join(path,fname)
                self.upload_file(full,folderid)
            for name,f in remote_file_map.items():
                if name not in local_files:
                    self.remove_file(f['id'],True)
            for name,f in remote_folder_map.items():
                if name not in local_dirs:
                    self.remove_folder(f['id'],True)
        sync_folder(local_path,parentid)

    def sync_remote_path(self, local_path, parentid=False):
        if parentid is False:
            parentid = self.get_root_folder_id()
            local_path = os.path.abspath(local_path)
            os.makedirs(local_path, exist_ok=True)
        def sync_folder(folderid, current_local_path):
            remote_folders = self.list_folders(folderid)
            for folder in remote_folders:
                folder_name = folder['name']
                folder_id = folder['id']
                new_local_path = os.path.join(current_local_path, folder_name)
                os.makedirs(new_local_path, exist_ok=True)
                sync_folder(folder_id, new_local_path)
            remote_files = self.list_files(folderid)
            for f in remote_files:
                file_id = f['id']
                file_name = f['name']
                local_file_path = os.path.join(current_local_path, file_name)
                if not os.path.exists(local_file_path):
                    print("Descargando " + local_file_path)
                    self.download_file(file_id, current_local_path)
                else:
                    print(local_file_path + " ya existe")
        sync_folder(parentid, local_path)

    def upload_local_path(self, local_path, parentid=False):
        # Non-destructive local -> cloud upload (Phase 1). Mirrors the local tree
        # into the cloud: creates missing folders and uploads files that don't
        # already exist remotely (matched by name). It NEVER deletes anything from
        # the cloud (unlike sync_local_path) and skips files that already exist.
        # Robust for large bulk uploads: skips over-size files, retries per file
        # and keeps going on errors (the run is resumable since it matches by name).
        if parentid is False:
            parentid = self.get_root_folder_id()
        local_path = os.path.abspath(local_path)
        max_bytes = self._max_upload_bytes()
        stats = {'uploaded': 0, 'exists': 0, 'too_big': 0, 'failed': 0}
        def sync_folder(path, folderid):
            entries = os.listdir(path)
            local_dirs = [e for e in entries if os.path.isdir(os.path.join(path, e))]
            local_files = [e for e in entries if os.path.isfile(os.path.join(path, e))]
            remote_folder_map = {f['name']: f for f in self.list_folders(folderid)}
            remote_file_map = {f['name']: f for f in self.list_files(folderid)}
            for d in local_dirs:
                if d in remote_folder_map:
                    child_id = remote_folder_map[d]['id']
                else:
                    print("Creando carpeta " + os.path.join(path, d))
                    self.create_folder(d, folderid)
                    remote_folder_map = {f['name']: f for f in self.list_folders(folderid)}
                    child_id = remote_folder_map[d]['id']
                sync_folder(os.path.join(path, d), child_id)
            for fname in local_files:
                full = os.path.join(path, fname)
                if fname in remote_file_map:
                    stats['exists'] += 1
                    print(full + " ya existe en el cloud")
                    continue
                size = os.path.getsize(full)
                if size > max_bytes:
                    stats['too_big'] += 1
                    print("SALTADO (%.0f MB > límite %.0f MB): %s" % (size / 1048576.0, max_bytes / 1048576.0, full))
                    continue
                try:
                    print("Subiendo " + full)
                    self.upload_file(full, folderid)
                    stats['uploaded'] += 1
                except SessionExpiredError:
                    raise  # no point continuing once the session is dead
                except Exception as e:
                    stats['failed'] += 1
                    print("ERROR subiendo %s: %s" % (full, e))
        sync_folder(local_path, parentid)
        print("Resumen subida -> subidos: %d, ya existían: %d, saltados (grandes): %d, fallidos: %d"
              % (stats['uploaded'], stats['exists'], stats['too_big'], stats['failed']))
        return stats
