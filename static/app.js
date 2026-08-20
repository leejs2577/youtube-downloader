document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('downloadForm');
    const urlInput = document.getElementById('urlInput');
    const formatRadios = document.getElementsByName('formatType');
    const resolutionGroup = document.getElementById('resolutionGroup');
    const resolutionSelect = document.getElementById('resolutionSelect');
    const downloadBtn = document.getElementById('downloadBtn');
    
    const statusMessage = document.getElementById('statusMessage');
    const statusText = document.getElementById('statusText');
    const videoInfo = document.getElementById('videoInfo');
    const videoTitle = document.getElementById('videoTitle');
    const thumbnail = document.getElementById('thumbnail');

    let fetchInfoTimeout = null;

    // Toggle resolution dropdown based on format selection
    formatRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            if (e.target.value === 'audio') {
                resolutionGroup.classList.add('hidden');
            } else {
                resolutionGroup.classList.remove('hidden');
            }
        });
    });

    // Fetch video info when a valid URL is pasted
    urlInput.addEventListener('input', (e) => {
        const url = e.target.value;
        if (url.includes('youtube.com/watch') || url.includes('youtu.be/')) {
            clearTimeout(fetchInfoTimeout);
            fetchInfoTimeout = setTimeout(() => {
                fetchVideoInfo(url);
            }, 1000);
        } else {
            videoInfo.classList.add('hidden');
        }
    });

    async function fetchVideoInfo(url) {
        showStatus('영상 정보를 불러오는 중...');
        downloadBtn.disabled = true;
        
        try {
            const response = await fetch(`/api/info?url=${encodeURIComponent(url)}`);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                if (errorData.detail) throw new Error(errorData.detail);
                throw new Error('정보를 불러오지 못했습니다.');
            }
            
            const data = await response.json();
            
            // Update UI
            videoTitle.textContent = data.title;
            thumbnail.src = data.thumbnail;
            videoInfo.classList.remove('hidden');
            
            // Update resolutions
            resolutionSelect.innerHTML = '<option value="best">최고 화질 (자동)</option>';
            if (data.resolutions && data.resolutions.length > 0) {
                data.resolutions.forEach(res => {
                    const option = document.createElement('option');
                    option.value = res;
                    option.textContent = res;
                    resolutionSelect.appendChild(option);
                });
            }
            
            hideStatus();
        } catch (error) {
            console.error(error);
            showStatus('오류: ' + error.message, true);
            setTimeout(hideStatus, 3000);
        } finally {
            downloadBtn.disabled = false;
        }
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const url = urlInput.value;
        let formatType = 'video';
        formatRadios.forEach(radio => {
            if (radio.checked) formatType = radio.value;
        });
        const resolution = resolutionSelect.value;
        
        if (!url) return;

        downloadBtn.disabled = true;
        showStatus('파일을 처리하고 다운로드 중입니다. 잠시만 기다려주세요...');
        
        try {
            const response = await fetch('/api/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    url: url,
                    format_type: formatType,
                    resolution: formatType === 'video' ? resolution : 'best'
                })
            });
            
            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || '다운로드에 실패했습니다.');
            }
            
            // Trigger file download
            const blob = await response.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            
            // Try to get filename from Content-Disposition header
            let filename = 'download';
            const disposition = response.headers.get('content-disposition');
            if (disposition && disposition.indexOf('filename=') !== -1) {
                let filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
                let matches = filenameRegex.exec(disposition);
                if (matches != null && matches[1]) { 
                    filename = matches[1].replace(/['"]/g, '');
                }
            } else {
                filename = formatType === 'video' ? 'video.mp4' : 'audio.mp3';
            }
            // Decode URI component for korean characters
            filename = decodeURIComponent(escape(filename));

            a.href = downloadUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(downloadUrl);
            a.remove();
            
            hideStatus();
        } catch (error) {
            console.error(error);
            showStatus('오류: ' + error.message, true);
            setTimeout(hideStatus, 4000);
        } finally {
            downloadBtn.disabled = false;
        }
    });

    function showStatus(message, isError = false) {
        statusMessage.classList.remove('hidden');
        statusText.textContent = message;
        
        const spinner = statusMessage.querySelector('.spinner');
        if (isError) {
            spinner.style.display = 'none';
            statusText.style.color = '#ff4444';
        } else {
            spinner.style.display = 'block';
            statusText.style.color = 'inherit';
        }
    }

    function hideStatus() {
        statusMessage.classList.add('hidden');
    }
});
