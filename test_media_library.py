import tempfile
import unittest
from pathlib import Path
from media_library import MediaLibrary,clean_title

class TestMediaLibrary(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.movies=self.root/'Filme'
        self.movies.mkdir()
        self.shows=self.root/'Serien'
        self.shows.mkdir()
        self.db=MediaLibrary(self.root/'settings')

    def test_scan_and_metadata(self):
        folder=self.movies/'Der Testfilm (2024)'
        folder.mkdir()
        (folder/'Der Testfilm (2024).mkv').write_bytes(b'TESTVIDEO')
        (folder/'movie.nfo').write_text('<movie><title>Der Testfilm</title><year>2024</year><genre>Thriller</genre><genre>Mystery</genre><plot>Lokale Beschreibung.</plot></movie>')
        season=self.shows/'Nordwind'/'Staffel 1'
        season.mkdir(parents=True)
        (self.shows/'Nordwind'/'tvshow.nfo').write_text('<tvshow><title>Nordwind</title><genre>Drama</genre><plot>Eigenes Serienarchiv.</plot></tvshow>')
        for i in (1,2):
            (season/f'Nordwind.S01E0{i}.mp4').write_bytes(b'FAKE-VIDEO'+bytes([i]))
        self.db.save({'sources':[{'path':str(self.movies),'type':'Film'},{'path':str(self.shows),'type':'Serie'}], 'auto_scan':True,'interval_minutes':15})
        self.assertEqual(self.db.scan()['count'],2)
        items=self.db.catalog()
        movie=next(x for x in items if x['type']=='Film')
        show=next(x for x in items if x['type']=='Serie')
        self.assertEqual(movie['title'],'Der Testfilm')
        self.assertEqual(movie['genre'],'Thriller')
        self.assertEqual(movie['genres'],['Thriller','Mystery'])
        self.assertEqual(movie['year'],2024)
        self.assertEqual(show['title'],'Nordwind')
        self.assertEqual(show['genre'],'Drama')
        self.assertEqual(len(show['episodes']),2)
        self.assertEqual(show['episodes'][1]['episode'],2)
        self.assertEqual(self.db.video(movie['id']).read_bytes(),b'TESTVIDEO')
        self.assertEqual(self.db.video(show['episodes'][0]['id']).suffix,'.mp4')

    def test_unknown_genre_not_invented(self):
        (self.movies/'Unbekannter Film (2020).mkv').write_bytes(b'MOCK')
        self.db.save({'sources':[{'path':str(self.movies),'type':'Auto'}], 'interval_minutes':30,'auto_scan':False})
        self.db.scan()
        item=self.db.catalog()[0]
        self.assertEqual(item['year'],2020)
        self.assertEqual(item['genre'],'Nicht zugeordnet')

    def test_invalid_paths_and_types(self):
        with self.assertRaises(ValueError):self.db.save({'sources':[{'path':str(self.root/'missing'),'type':'Film'}]})
        with self.assertRaises(ValueError):self.db.save({'sources':[{'path':str(self.root),'type':'Wrong'}]})
        with self.assertRaises(ValueError):self.db.save({'sources':[], 'interval_minutes':1})

    def test_symlinks_skipped(self):
        external=self.root/'outside.mkv'
        external.write_bytes(b'TEST')
        (self.movies/'link.mkv').symlink_to(external)
        self.db.save({'sources':[{'path':str(self.movies),'type':'Film'}]})
        self.assertEqual(self.db.scan()['count'],0)

if __name__=='__main__':unittest.main()
