import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { ApiService } from '../../services/api.service';
import { FormResponse, FormRow } from '../../models';

@Component({
  selector: 'app-analytics',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './analytics.component.html',
  styleUrls: ['./analytics.component.css']
})
export class AnalyticsComponent implements OnInit {
  data: FormRow[] = [];
  loading = false;
  error = '';

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading = true;
    this.api.fetchFormAnalytics().subscribe({
      next: (res: FormResponse) => {
        this.data = res.data;
        this.loading = false;
      },
      error: (err) => {
        this.error = err?.error?.message || 'Unable to fetch analytics';
        this.loading = false;
      }
    });
  }
}
