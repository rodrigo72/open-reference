import os
import shutil
import uuid
import tempfile
from PIL import Image, ImageOps
from tqdm import tqdm
from multiprocessing import Pool, cpu_count


def should_compress(image_path,
                    size_threshold=500*1024,
                    width_threshold=1920,
                    height_threshold=1080,
                    formats_to_compress=(".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp"),
                    debug=False):
    
    if not os.path.exists(image_path):
        return False

    ext = os.path.splitext(image_path)[1].lower()
    if ext not in formats_to_compress:
        return False

    try:
        file_size = os.path.getsize(image_path)
        if file_size < size_threshold:
            return False
    except OSError:
        return False

    try:
        with Image.open(image_path) as img:
            width, height = img.size
            if width < width_threshold and height < height_threshold:
                return False
    except Exception:
        return False

    return True


def compress_image(image_path, quality=85, backup=True, debug=False):
    created_backup = False
    backup_path = None
    temp_file = None
    original_mode = None
    new_filename = None

    try:
        if backup:
            backup_path = f"{image_path}.bak"
            shutil.copy2(image_path, backup_path)
            created_backup = True
            if debug:
                print(f"Created backup at {backup_path}")

        original_mode = os.stat(image_path).st_mode

        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            ext = os.path.splitext(image_path)[1].lower()
            save_args = {}

            if ext in ['.tiff']:
                new_ext = '.tiff'
                save_args = {'format': 'TIFF', 'compression': 'tiff_lzw'}
            elif ext == '.bmp':
                new_ext = '.png'
                save_args = {'format': 'PNG', 'optimize': True}
            elif ext in ['.jpg', '.jpeg']:
                new_ext = '.jpg'
                save_args = {
                    'format': 'JPEG',
                    'quality': quality,
                    'optimize': True,
                    'progressive': False,
                    'subsampling': '4:2:0'
                }
                img = img.convert('RGB')
            elif ext == '.png':
                new_ext = '.png'
                save_args = {
                    'format': 'PNG', 
                    'compress_level': 9 if os.path.getsize(image_path) > 2*1024*1024 else 6,
                    'optimize': True
                }
            elif ext == '.webp':
                new_ext = '.webp'
                save_args = {'format': 'WEBP', 'quality': quality}
            else:
                return False

            # create temp file in same directory as original
            temp_dir = os.path.dirname(image_path)
            with tempfile.NamedTemporaryFile(
                dir=temp_dir,
                delete=False,
                suffix=new_ext,
                prefix=os.path.basename(image_path) + "."
            ) as tmp_file:
                img.save(tmp_file, **save_args)
                temp_file = tmp_file.name

            # verify compressed file
            try:
                with Image.open(temp_file) as test_img:
                    test_img.verify()
            except Exception as e:
                if debug:
                    print(f"File verification failed: {str(e)}")
                os.remove(temp_file)
                return False

            base_name = os.path.splitext(image_path)[0]
            new_filename = f"{base_name}{new_ext}"

            if new_filename != image_path:
                if os.path.exists(new_filename):
                    unique_id = uuid.uuid4().hex[:8]
                    new_filename = f"{base_name}_{unique_id}{new_ext}"

            # cross-device safe replacement
            shutil.move(temp_file, new_filename)

            # clean up original if needed
            if new_filename != image_path and os.path.exists(image_path):
                os.remove(image_path)

            # preserve permissions
            os.chmod(new_filename, original_mode)

            # remove backup after successful compression
            if created_backup and backup_path:
                os.remove(backup_path)
                if debug:
                    print(f"Removed backup {backup_path}")

            return True

    except Exception as e:
        if debug:
            print(f"Error processing {image_path}: {str(e)}")

        # clean up temp file
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception as clean_error:
                if debug:
                    print(f"Failed to clean temp file: {str(clean_error)}")

        # handle backup restoration
        if created_backup and backup_path:
            try:
                original_exists = os.path.exists(image_path)
                new_exists = os.path.exists(new_filename) if new_filename else False

                if not original_exists and not new_exists:
                    shutil.move(backup_path, image_path)
                    if debug:
                        print(f"Restored original from backup: {image_path}")
                elif original_exists:
                    os.remove(backup_path)
                    if debug:
                        print(f"Removed unnecessary backup: {backup_path}")
            except Exception as restore_error:
                if debug:
                    print(f"Backup handling failed: {str(restore_error)}")

        return False


def process_single_file(args):
    """Worker function for parallel processing"""
    image_path, quality = args
    result = {
        'success': False,
        'original_size': 0,
        'compressed_size': 0
    }
    
    try:
        original_size = os.path.getsize(image_path)
    except OSError:
        return result
    
    success = compress_image(image_path, quality, backup=True, debug=False)
    
    if success:
        try:
            if os.path.splitext(image_path)[1].lower() == '.bmp':
                new_path = os.path.splitext(image_path)[0] + '.png'
            else:
                new_path = image_path
            compressed_size = os.path.getsize(new_path)
        except OSError:
            compressed_size = 0
            
        result.update({
            'success': True,
            'original_size': original_size,
            'compressed_size': compressed_size
        })
    
    return result


def process_directory(directory, quality=85):
    all_files = []
    for root, _, files in os.walk(directory, followlinks=False):
        for file in files:
            all_files.append(os.path.join(root, file))

    # pre-filter files that need compression
    files_to_compress = []
    skipped_count = 0
    
    for path in all_files:
        if should_compress(path):
            files_to_compress.append((path, quality))
        else:
            skipped_count += 1

    compressed_count = 0
    failed_count = 0
    total_original = 0
    total_compressed = 0

    num_workers = 4  # or cpu_count()
    
    with Pool(processes=num_workers) as pool:
        with tqdm(total=len(files_to_compress), desc="Processing Images") as pbar:
            results = []
            
            # process files in parallel
            for result in pool.imap_unordered(process_single_file, files_to_compress):
                if result['success']:
                    compressed_count += 1
                    total_original += result['original_size']
                    total_compressed += result['compressed_size']
                else:
                    failed_count += 1
                pbar.update(1)

    size_diff = total_original - total_compressed
    reduction_pct = (size_diff / total_original * 100) if total_original > 0 else 0

    print("\nCompression Report:")
    print(f"Total Files Processed: {len(all_files)}")
    print(f"Successfully Compressed: {compressed_count}")
    print(f"Failed to Compress: {failed_count}")
    print(f"Skipped (Not Eligible): {skipped_count}")
    
    print("\nSize Statistics:")
    print(f"Total Original Size: {total_original / (1024 * 1024):.2f} MB")
    print(f"Total Compressed Size: {total_compressed / (1024 * 1024):.2f} MB")
    print(f"Total Size Reduction: {size_diff / (1024 * 1024):.2f} MB ({reduction_pct:.2f}%)")


if __name__ == "__main__":
    dir_path = ""
    process_directory(dir_path, quality=80)


""" 
Processing Images: 100%|█| 49811/49811 [1:15:39<00:00

Compression Report:
Total Files Processed: 63028
Successfully Compressed: 49807
Failed to Compress: 4
Skipped (Not Eligible): 13217

Size Statistics:
Total Original Size: 164386.99 MB
Total Compressed Size: 71694.50 MB
Total Size Reduction: 92692.49 MB (56.39%)

---

Compression Report:
Total Files Processed: 22883
Successfully Compressed: 19855
Failed to Compress: 0
Skipped (Not Eligible): 3028

Size Statistics:
Total Original Size: 72079.42 MB
Total Compressed Size: 26859.96 MB
Total Size Reduction: 45219.46 MB (62.74%)

"""