package main

import "testing"

func TestNormalizePairingPhone(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		want    string
		wantErr bool
	}{
		{name: "international with plus", input: "+212600000000", want: "212600000000"},
		{name: "international digits", input: "212600000000", want: "212600000000"},
		{name: "leading zero", input: "0612345678", wantErr: true},
		{name: "contains spaces", input: "+212 600000000", wantErr: true},
		{name: "too short", input: "123456", wantErr: true},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got, err := normalizePairingPhone(test.input)
			if test.wantErr {
				if err == nil {
					t.Fatalf("expected an error, got %q", got)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got != test.want {
				t.Fatalf("got %q, want %q", got, test.want)
			}
		})
	}
}
