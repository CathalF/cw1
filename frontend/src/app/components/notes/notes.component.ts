import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';
import { Match, Note } from '../../models';

@Component({
  selector: 'app-notes',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './notes.component.html',
  styleUrls: ['./notes.component.css']
})
export class NotesComponent implements OnInit {
  matchId = '';
  match?: Match;
  notes: Note[] = [];
  noteText = '';
  error = '';
  loading = false;

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    public auth: AuthService
  ) {}

  ngOnInit(): void {
    this.matchId = this.route.snapshot.paramMap.get('matchId') || '';
    if (this.matchId) {
      this.load();
    }
  }

  load(): void {
    this.loading = true;
    this.api.getMatch(this.matchId).subscribe((m) => (this.match = m));
    this.api.listNotes(this.matchId).subscribe({
      next: (list) => {
        this.notes = list;
        this.loading = false;
      },
      error: (err) => {
        this.error = err?.error?.message || 'Unable to fetch notes';
        this.loading = false;
      }
    });
  }

  saveNote(): void {
    if (!this.noteText.trim()) {
      this.error = 'Write something before submitting';
      return;
    }
    this.error = '';
    this.api.createNote(this.matchId, this.noteText).subscribe({
      next: (note) => {
        this.notes = [...this.notes, note];
        this.noteText = '';
      },
      error: (err) => {
        this.error = err?.error?.message || 'Unable to save note';
      }
    });
  }

  delete(id: string): void {
    this.api.deleteNote(id).subscribe(() => {
      this.notes = this.notes.filter((n) => n.id !== id);
    });
  }
}
